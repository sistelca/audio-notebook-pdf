import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_NAME = os.path.join(BASE_DIR, 'notebook.db')

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT UNIQUE,
            title TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chapters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER,
            chapter_number INTEGER,
            title TEXT,
            start_page INTEGER,
            end_page INTEGER,
            content TEXT,
            FOREIGN KEY(book_id) REFERENCES books(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS progress (
            book_id INTEGER PRIMARY KEY,
            current_chapter_id INTEGER,
            current_paragraph INTEGER DEFAULT 0,
            FOREIGN KEY(book_id) REFERENCES books(id),
            FOREIGN KEY(current_chapter_id) REFERENCES chapters(id)
        )
    ''')

    conn.commit()
    conn.close()

def save_book_and_chapters(filename, chapters):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Insertar o buscar libro
    cursor.execute("INSERT OR IGNORE INTO books (filename, title) VALUES (?, ?)", (filename, filename))
    cursor.execute("SELECT id FROM books WHERE filename = ?", (filename,))
    book_id = cursor.fetchone()[0]

    # LIMPIAR CAPÍTULOS VIEJOS del libro para evitar duplicados al recargar
    cursor.execute("DELETE FROM chapters WHERE book_id = ?", (book_id,))

    # Insertar capítulos nuevos y limpios
    for cap in chapters:
        cursor.execute('''
            INSERT INTO chapters 
            (book_id, chapter_number, title, start_page, end_page, content)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (book_id, cap['chapter_number'], cap['title'], cap['start_page'], cap['end_page'], cap['text']))

    # Inicializar progreso en el primer capítulo
    cursor.execute("SELECT id FROM chapters WHERE book_id = ? ORDER BY chapter_number ASC LIMIT 1", (book_id,))
    first_chap = cursor.fetchone()
    if first_chap:
        cursor.execute("INSERT OR IGNORE INTO progress (book_id, current_chapter_id) VALUES (?, ?)", (book_id, first_chap[0]))

    conn.commit()
    conn.close()
    return book_id