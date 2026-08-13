import os
from flask import Flask, render_template, jsonify, request
from services.pdf_processor import PDFChapterExtractor
import services.database as db

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORAGE_FOLDER = os.path.join(BASE_DIR, 'storage')

os.makedirs(STORAGE_FOLDER, exist_ok=True)
db.init_db()

@app.route('/')
def index():
    # Escanear carpeta storage para procesar PDFs locales
    pdf_files = [f for f in os.listdir(STORAGE_FOLDER) if f.endswith('.pdf')]
    
    for pdf in pdf_files:
        path = os.path.join(STORAGE_FOLDER, pdf)
        extractor = PDFChapterExtractor(path)
        capitulos = extractor.get_chapters()
        if capitulos:
            db.save_book_and_chapters(pdf, capitulos)

    # Obtener lista de libros procesados de la BD
    import sqlite3
    conn = sqlite3.connect(db.DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM books")
    books = cursor.fetchall()
    conn.close()

    return render_template('index.html', books=books)

@app.route('/book/<int:book_id>/chapters')
def get_chapters(book_id):
    import sqlite3
    conn = sqlite3.connect(db.DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, chapter_number, title, start_page, end_page FROM chapters WHERE book_id = ? ORDER BY chapter_number", (book_id,))
    rows = cursor.fetchall()
    
    # Obtener el progreso
    cursor.execute("SELECT current_chapter_id FROM progress WHERE book_id = ?", (book_id,))
    prog = cursor.fetchone()
    current_chap_id = prog[0] if prog else (rows[0][0] if rows else None)
    
    conn.close()
    
    chapters = [{"id": r[0], "number": r[1], "title": r[2], "pages": f"{r[3]}-{r[4]}"} for r in rows]
    return jsonify({"chapters": chapters, "current_chapter_id": current_chap_id})

@app.route('/chapter/<int:chapter_id>')
def get_chapter_content(chapter_id):
    import sqlite3
    conn = sqlite3.connect(db.DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, book_id, title, content FROM chapters WHERE id = ?", (chapter_id,))
    row = cursor.fetchone()
    
    if row:
        # Guardar como último capítulo leído
        cursor.execute("UPDATE progress SET current_chapter_id = ? WHERE book_id = ?", (chapter_id, row[1]))
        conn.commit()
        conn.close()
        
        # Dividimos el texto en párrafos para poder pausar/resaltar
        paragraphs = [p.strip() for p in row[3].split('\n\n') if p.strip()]
        return jsonify({
            "id": row[0],
            "title": row[2],
            "paragraphs": paragraphs
        })
    conn.close()
    return jsonify({"error": "No encontrado"}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)