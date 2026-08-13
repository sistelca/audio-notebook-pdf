import pymupdf

def extract_chapters_from_pdf(pdf_path):
    """
    Extrae los capítulos de un PDF priorizando la tabla de contenidos (TOC) nativa.
    Si no existe TOC, aplica un fallback para no perder ni truncar información.
    """
    doc = pymupdf.open(pdf_path)
    toc = doc.get_toc()  # Devuelve una lista: [nivel, título, página_inicio]
    
    chapters = []
    
    # -------------------------------------------------------------
    # ESTRATEGIA 1: Usar la Tabla de Contenidos (TOC / Índice) nativa
    # -------------------------------------------------------------
    if toc:
        # Filtramos solo los capítulos principales (por ejemplo, nivel 1 o 2)
        # toc structure: [level, title, page_number]
        chapters_toc = [item for item in toc if item[0] in [1, 2]]
        
        for i, item in enumerate(chapters_toc):
            title = item[1].strip()
            start_page = item[2] - 1  # PyMuPDF usa índices de página base 0
            
            # La página final será la página anterior al siguiente capítulo, 
            # o el final del documento si es el último capítulo.
            if i + 1 < len(chapters_toc):
                end_page = chapters_toc[i + 1][2] - 1
            else:
                end_page = len(doc)
            
            # Extraer todo el texto acumulado entre start_page y end_page
            chapter_text = ""
            for page_num in range(start_page, max(start_page + 1, end_page)):
                if page_num < len(doc):
                    chapter_text += doc[page_num].get_text("text") + "\n"
            
            if chapter_text.strip():
                chapters.append({
                    "number": i + 1,
                    "title": title,
                    "text": chapter_text.strip()
                })

    # -------------------------------------------------------------
    # ESTRATEGIA 2: Respaldo (Fallback) si el PDF no tiene TOC
    # -------------------------------------------------------------
    if not chapters:
        full_text = ""
        for page in doc:
            full_text += page.get_text("text") + "\n"
            
        # Si no hay índice, guardamos el documento en un solo bloque completo 
        # para evitar truncar información.
        chapters.append({
            "number": 1,
            "title": "Documento Completo",
            "text": full_text.strip()
        })
        
    doc.close()
    return chapters
