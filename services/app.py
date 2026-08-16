import os
import json
import sqlite3
from flask import Flask, render_template, jsonify, request
from services.pdf_processor import PDFChapterExtractor
from services.qa_engine import ChapterQAEngine
import services.database as db
from services.utils.logger import get_logger

logger = get_logger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORAGE_FOLDER = os.path.join(BASE_DIR, 'storage')

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
    qa_engine = ChapterQAEngine()
except Exception as e:
    logger.exception(f"⚠️ Advertencia QA Engine: {e}")

@app.route('/')
def index():
    """Carga la página de forma INSTANTÁNEA sin esperar a Gemini"""
    conn = sqlite3.connect(db.DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM books")
    books = cursor.fetchall()
    conn.close()

    # Renders la vista en milisegundos
    return render_template('index.html', books=books)

@app.route('/api/process-books', methods=['POST'])
def process_books():
    """
    Endpoint invocado en segundo plano por el JavaScript.
    Procesa únicamente los PDFs nuevos que no estén en SQLite.
    """
    pdf_files = [f for f in os.listdir(STORAGE_FOLDER) if f.endswith('.pdf')]
    
    conn = sqlite3.connect(db.DB_NAME)
    cursor = conn.cursor()
    
    nuevos_procesados = 0

    for pdf in pdf_files:
        # Verificar si el PDF ya fue procesado antes
        cursor.execute("SELECT id FROM books WHERE title = ?", (pdf,))
        if not cursor.fetchone():
            path = os.path.join(STORAGE_FOLDER, pdf)
            try:
                extractor = PDFChapterExtractor(path)
                capitulos = extractor.get_chapters()
                if capitulos:
                    db.save_book_and_chapters(pdf, capitulos)
                    nuevos_procesados += 1
            except Exception as e:
                logger.exception(f"⚠️ Error procesando {pdf}: {e}")

    conn.close()
    return jsonify({"status": "ok", "processed": nuevos_procesados})

@app.route('/book/<int:book_id>/chapters')
def get_chapters(book_id):
    conn = sqlite3.connect(db.DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT structure FROM books WHERE id = ?", (book_id,))
    resultado = cursor.fetchone()

    chapters = db.load_chapters(resultado)
    
    cursor.execute("SELECT current_chapter_id FROM progress WHERE book_id = ?", (book_id,))
    prog = cursor.fetchone()

    current_chap_id = prog[0] if prog else 0
    conn.close()
    
    return jsonify({"chapters": chapters, "current_chapter_id": current_chap_id})

@app.route('/chapter/<bookchap_id>')
def get_chapter_content(bookchap_id):

    conn = sqlite3.connect(db.DB_NAME)
    book_id = int(bookchap_id.split('_')[0])
    chapter_id = int(bookchap_id.split('_')[1])
    chapter = None

    cursor = conn.cursor()
    cursor.execute("SELECT filename, structure FROM books WHERE id = ?", (book_id,))
    resultado = cursor.fetchone()

    if resultado:
        pdf = resultado[0]
        chapters = db.load_chapters(resultado, 1)

        path = os.path.join(STORAGE_FOLDER, pdf)
        extractor = PDFChapterExtractor(path)
        chapter = extractor.get_chapter(chapters, chapter_id)
        paragraphs = ' '.join(chapters['paragraphs'])

    if chapter:
        cursor.execute("""
            INSERT INTO progress (book_id, current_chapter_id, chapter_content, current_paragraph)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(book_id) DO UPDATE SET
                current_chapter_id = excluded.current_chapter_id,
                chapter_content = excluded.chapter_content,
                current_paragraph = excluded.current_paragraph
        """, (book_id, chapter_id, paragraphs, chapter_id))

        conn.commit()
        conn.close()
        
        return jsonify(
            chapter
        )
    conn.close()
    return jsonify({"error": "No encontrado"}), 404

@app.route('/ask', methods=['POST'])
def ask_question():
    if not qa_engine:
        return jsonify({"error": "El motor de IA no está configurado (GEMINI_API_KEY faltante)."}), 500

    data = request.json
    book_chapter_id = data.get("chapter_id")
    book_id = int(book_chapter_id.split('_')[0])
    chapter_id = int(book_chapter_id.split('_')[1])

    question = data.get("question")

    if not chapter_id or not question:
        return jsonify({"error": "Faltan parámetros requeridos."}), 400

    # Obtener el contenido completo del capítulo desde la BD
    conn = sqlite3.connect(db.DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT chapter_content FROM progress WHERE book_id = ?", (book_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "Capítulo no encontrado."}), 404

    chapter_text = row[0]
    
    try:
        answer = qa_engine.ask_chapter(chapter_text, question)
        return jsonify({"answer": answer})
    except Exception as e:
        return jsonify({"error": f"Error al procesar la respuesta: {str(e)}"}), 500