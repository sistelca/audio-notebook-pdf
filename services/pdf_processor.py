import pymupdf
import re

class PDFChapterExtractor:
    def __init__(self, pdf_path):
        self.pdf_path = pdf_path
        self.doc = pymupdf.open(pdf_path)

    def get_chapters(self):
        toc = self.doc.get_toc()
        total_pages = len(self.doc)

        # Si no hay TOC o es diminuta, parseamos por páginas de forma lineal
        if not toc or len(toc) < 3:
            return self._extract_by_fixed_chunks()

        # Filtrar entradas válidas eliminando duplicados en la misma página
        filtered_toc = []
        seen_pages = set()

        for item in toc:
            level, title, page = item
            # Solo tomamos niveles principales (1 y 2) y evitamos repetir la misma página varias veces
            if level <= 2 and page > 0 and page <= total_pages:
                if page not in seen_pages:
                    filtered_toc.append((title, page))
                    seen_pages.add(page)

        if not filtered_toc:
            return self._extract_by_fixed_chunks()

        chapters = []
        for i, (title, start_page) in enumerate(filtered_toc):
            # Calcular página final basada en el inicio del siguiente marcador
            if i + 1 < len(filtered_toc):
                end_page = filtered_toc[i + 1][1] - 1
            else:
                end_page = total_pages

            # Asegurar que al menos lea 1 página si end_page quedó igual o menor a start_page
            if end_page < start_page:
                end_page = start_page

            content = self._get_text_range(start_page - 1, end_page)

            # Si el contenido está vacío (por ejemplo imágenes/portadas), forzamos lectura extendida
            if len(content.strip()) < 50 and end_page < total_pages:
                end_page = min(start_page + 5, total_pages)
                content = self._get_text_range(start_page - 1, end_page)

            if content.strip():
                chapters.append({
                    "chapter_number": len(chapters) + 1,
                    "title": title.strip(),
                    "start_page": start_page,
                    "end_page": end_page,
                    "text": content.strip()
                })

        return chapters

    def _get_text_range(self, start_idx, end_idx):
        full_text = ""
        for p in range(start_idx, end_idx):
            if p < len(self.doc):
                text = self.doc[p].get_text("text").strip()
                if text:
                    full_text += f"\n--- Página {p + 1} ---\n" + text + "\n"
        return full_text

    def _extract_by_fixed_chunks(self):
        """Método de respaldo si la TOC no sirve: agrupa por bloques de páginas."""
        chapters = []
        total = len(self.doc)
        chunk_size = 15  # Secciones de 15 páginas si no hay índice
        
        for i in range(0, total, chunk_size):
            start = i + 1
            end = min(i + chunk_size, total)
            text = self._get_text_range(i, end)
            chapters.append({
                "chapter_number": len(chapters) + 1,
                "title": f"Sección {len(chapters) + 1} (Págs. {start}-{end})",
                "start_page": start,
                "end_page": end,
                "text": text
            })
        return chapters