import os
import sqlite3
from flask import Flask, render_template, jsonify, request
from services.pdf_processor import PDFChapterExtractor
from services.qa_engine import ChapterQAEngine
import services.database as db
from google import genai


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORAGE_FOLDER = os.path.join(BASE_DIR, 'storage')

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY no está configurada en las variables de entorno.")

client = genai.Client(api_key=api_key)

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
    static_folder=os.path.join(os.path.dirname(__file__), 'static')
)

os.makedirs(STORAGE_FOLDER, exist_ok=True)
db.init_db()

# Inicializamos el motor de IA si la clave de API está configurada
qa_engine = None
try:
    qa_engine = ChapterQAEngine(client)
except Exception as e:
    print(f"⚠️ Advertencia QA Engine: {e}")

@app.route('/')
def index():
    pdf_files = [f for f in os.listdir(STORAGE_FOLDER) if f.endswith('.pdf')]
    for pdf in pdf_files:
        path = os.path.join(STORAGE_FOLDER, pdf)
        extractor = PDFChapterExtractor(path)
        capitulos = extractor.get_chapters()
        if capitulos:
            db.save_book_and_chapters(pdf, capitulos)

    conn = sqlite3.connect(db.DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM books")
    books = cursor.fetchall()
    conn.close()

    return render_template('index.html', books=books)

@app.route('/book/<int:book_id>/chapters')
def get_chapters(book_id):
    conn = sqlite3.connect(db.DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, chapter_number, title, start_page, end_page FROM chapters WHERE book_id = ? ORDER BY chapter_number", (book_id,))
    rows = cursor.fetchall()
    
    cursor.execute("SELECT current_chapter_id FROM progress WHERE book_id = ?", (book_id,))
    prog = cursor.fetchone()
    current_chap_id = prog[0] if prog else (rows[0][0] if rows else None)
    conn.close()
    
    chapters = [{"id": r[0], "number": r[1], "title": r[2], "pages": f"{r[3]}-{r[4]}"} for r in rows]
    return jsonify({"chapters": chapters, "current_chapter_id": current_chap_id})

@app.route('/chapter/<int:chapter_id>')
def get_chapter_content(chapter_id):
    conn = sqlite3.connect(db.DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, book_id, title, content FROM chapters WHERE id = ?", (chapter_id,))
    row = cursor.fetchone()
    
    if row:
        cursor.execute("UPDATE progress SET current_chapter_id = ? WHERE book_id = ?", (chapter_id, row[1]))
        conn.commit()
        conn.close()
        
        paragraphs = [p.strip() for p in row[3].split('\n\n') if p.strip()]
        return jsonify({
            "id": row[0],
            "title": row[2],
            "paragraphs": paragraphs
        })
    conn.close()
    return jsonify({"error": "No encontrado"}), 404

@app.route('/ask', methods=['POST'])
def ask_question():
    if not qa_engine:
        return jsonify({"error": "El motor de IA no está configurado (GEMINI_API_KEY faltante)."}), 500

    data = request.json
    chapter_id = data.get("chapter_id")
    question = data.get("question")

    if not chapter_id or not question:
        return jsonify({"error": "Faltan parámetros requeridos."}), 400

    # Obtener el contenido completo del capítulo desde la BD
    conn = sqlite3.connect(db.DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT title, content FROM chapters WHERE id = ?", (chapter_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "Capítulo no encontrado."}), 404

    chapter_title, chapter_text = row
    
    try:
        answer = qa_engine.ask_chapter(chapter_title, chapter_text, question)
        return jsonify({"answer": answer})
    except Exception as e:
        return jsonify({"error": f"Error al procesar la respuesta: {str(e)}"}), 500