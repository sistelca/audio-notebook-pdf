import pymupdf
import re
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# ------------------------------------------------------------------
# 1. Esquema Pydantic para la respuesta de Gemini
# ------------------------------------------------------------------
class ElementoIndice(BaseModel):
    nivel: str = Field(description="Tipo de jerarquía: 'parte', 'capitulo', 'seccion'")
    numero: str = Field(description="Número identificador. Ej: '1', '2', '2.5'")
    titulo: str = Field(description="Título limpio sin puntos guía ni número de página")
    pagina_impresa: int = Field(description="Página listada en el índice impreso")

class EsqueletoLibro(BaseModel):
    estructura: list[ElementoIndice]


# ------------------------------------------------------------------
# 2. Clase Extractora con Delimitación Exacta de Texto
# ------------------------------------------------------------------
class PDFChapterExtractor:
    def __init__(self, pdf_path: str, client):
        self.pdf_path = pdf_path
        self.doc = pymupdf.open(pdf_path)
        self.client = client

    def get_chapters(self) -> list[dict]:
        # Paso 1: Consultar a Gemini el índice impreso en las primeras páginas
        esqueleto = self._extraer_esqueleto_gemini()
        if not esqueleto or not esqueleto.estructura:
            return []

        # Asumimos que los preliminares e índice están en las primeras 15 páginas
        PAGINAS_PRELIMINARES = min(15, len(self.doc))

        # Paso 2: Crear el buffer de texto continuo (post-índice) y mapear caracteres a páginas
        full_text = ""
        char_to_page = []  # Lista donde char_to_page[i] me dice en qué página está el caracter i

        for page_idx in range(PAGINAS_PRELIMINARES, len(self.doc)):
            page_num = page_idx + 1
            page_text = self.doc[page_idx].get_text("text")
            
            for char in page_text:
                full_text += char
                char_to_page.append(page_num)
            
            # Agregamos un salto de línea entre páginas
            full_text += "\n"
            char_to_page.append(page_num)

        if not full_text:
            return []

        # Paso 3: Buscar las posiciones exactas de cada título de forma secuencial
        titulos_posiciones = []
        current_search_idx = 0

        for item in esqueleto.estructura:
            titulo_clean = item.titulo.strip()
            
            # Búsqueda flexible usando Regex para tolerar saltos de línea o múltiples espacios en el título
            pattern = re.escape(titulo_clean).replace(r'\ ', r'\s+')
            match = re.search(pattern, full_text[current_search_idx:], re.IGNORECASE)

            if match:
                # Posición absoluta dentro del full_text
                abs_start_idx = current_search_idx + match.start()
                page_start = char_to_page[min(abs_start_idx, len(char_to_page) - 1)]

                titulos_posiciones.append({
                    "numero": item.numero if item.numero else "",
                    "titulo": item.titulo,
                    "start_idx": abs_start_idx,
                    "start_page": page_start
                })
                # El siguiente título DEBE buscarse a partir de donde comenzó este
                current_search_idx = abs_start_idx + len(match.group(0))

        # Paso 4: Recortar el texto EXACTO de título a título
        resultado = []
        total_titulos = len(titulos_posiciones)

        for i, item in enumerate(titulos_posiciones):
            start_idx = item["start_idx"]
            start_page = item["start_page"]

            if i + 1 < total_titulos:
                end_idx = titulos_posiciones[i + 1]["start_idx"]
                end_page = titulos_posiciones[i + 1]["start_page"]
            else:
                end_idx = len(full_text)
                end_page = char_to_page[-1] if char_to_page else len(self.doc)

            # Extraemos el texto exacto desde el inicio del título actual hasta justo antes del siguiente
            content_exacto = full_text[start_idx:end_idx].strip()

            resultado.append({
                "chapter_number": item["numero"],
                "title": item["titulo"],
                "start_page": start_page,
                "end_page": end_page,
                "content": content_exacto
            })

        return resultado

    def _extraer_esqueleto_gemini(self) -> EsqueletoLibro:
        """Extrae el texto de los preliminares y obtiene la estructura JSON con Gemini"""
        texto_preliminares = ""
        paginas_analizar = min(15, len(self.doc))
        
        for i in range(paginas_analizar):
            texto_preliminares += f"\n--- PÁGINA FÍSICA {i + 1} ---\n"
            texto_preliminares += self.doc[i].get_text("text")

        prompt = f"""
        Analiza el texto de los preliminares de este libro y extrae la Tabla de Contenido / Índice.
        Extrae únicamente las entradas correspondientes a Partes, Capítulos o Secciones principales.

        Texto:
        {texto_preliminares}
        """

        try:
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=EsqueletoLibro,
                    temperature=0.0
                ),
            )
            return response.parsed
        except Exception as e:
            print(f"❌ Error consultando Gemini para índice: {e}")
            return EsqueletoLibro(estructura=[])