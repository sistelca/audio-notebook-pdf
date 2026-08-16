import sqlite3
import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_NAME = os.path.join(DATA_DIR, 'notebook.db')
from utils.logger import get_logger

logger = get_logger(__name__)

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT UNIQUE,
            title TEXT,
            structure TEXT CONSTRAINT json_valido CHECK (json_valid(structure))
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS progress (
            book_id INTEGER PRIMARY KEY,
            current_chapter_id INTEGER,
            chapter_content TEXT,
            current_paragraph INTEGER DEFAULT 0,
            FOREIGN KEY(book_id) REFERENCES books(id)
        )
    ''')

    conn.commit()
    conn.close()

def save_book_and_chapters(filename, chapters):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Insertar o buscar libro
    cursor.execute("INSERT OR IGNORE INTO books (filename, title, structure) VALUES (?, ?)", (filename, filename, chapters))
    cursor.execute("SELECT id FROM books WHERE filename = ?", (filename,))
    book_id = cursor.fetchone()[0]

    conn.commit()
    conn.close()
    return book_id

def load_chapters(resultado, i=0):
    chapters = []
    try:
        if resultado:
            for elemento in json.loads(resultado[i]):
                if elemento.get('nivel') in [0, 1, 2, 3]:
                    chapters.append(elemento)

    except Exception as e:
        logger.exception(f"❌ load_chapters: {e}")

    return chapters
