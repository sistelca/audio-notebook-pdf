import pymupdf
import re
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# ------------------------------------------------------------------
# 1. Esquema Pydantic para Gemini
# ------------------------------------------------------------------
class ElementoIndice(BaseModel):
    numero: str = Field(description="Identificador del capítulo/sección. Ej: '1', '2.5', 'Capítulo 3'")
    titulo: str = Field(description="Título limpio de la sección")

class EsqueletoLibro(BaseModel):
    estructura: list[ElementoIndice]


# ------------------------------------------------------------------
# 2. Extractora Ultra Rápida por Marcadores (XX -> YX)
# ------------------------------------------------------------------
class PDFChapterExtractor:
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.doc = pymupdf.open(pdf_path)
        self.client = genai.Client()

    def get_chapters(self) -> list[dict]:
        # 1. Obtener los marcadores (números de capítulo) desde Gemini
        esqueleto = self._extraer_esqueleto_gemini()
        if not esqueleto or not esqueleto.estructura:
            return []

        PAGINAS_PRELIMINARES = min(15, len(self.doc))

        # 2. Concatenación instantánea del texto post-índice
        # PyMuPDF extrae todo el libro en < 10ms usando join
        full_text = "\n".join(
            self.doc[p].get_text("text") for p in range(PAGINAS_PRELIMINARES, len(self.doc))
        )

        if not full_text:
            return []

        # 3. Encontrar las posiciones de corte (Búsqueda de XX -> YX)
        posiciones = []
        cursor_pos = 0

        for item in esqueleto.estructura:
            num = item.numero.strip()
            if not num:
                continue

            # Construimos un patrón regex que busque el número al inicio de línea o rodeado de espacios
            # Ejemplo: Busca "2.5" o "Capítulo 2.5"
            pattern = r'(?:^|\n|\s+)' + re.escape(num) + r'(?:\s+|\.|$)'
            
            match = re.search(pattern, full_text[cursor_pos:], re.IGNORECASE)

            if match:
                start_idx = cursor_pos + match.start()
                posiciones.append({
                    "numero": num,
                    "titulo": item.titulo,
                    "start_idx": start_idx
                })
                # Avanzamos el cursor para buscar el SIGUIENTE capítulo estrictamente después de este
                cursor_pos = start_idx + len(match.group(0))

        # 4. Generar la estructura con recortes exactos XX -> YX
        resultado = []
        total = len(posiciones)

        for i, pos in enumerate(posiciones):
            start = pos["start_idx"]
            # Si hay un siguiente capítulo (YX), el corte termina justo allí. Si no, llega al final del texto.
            end = posiciones[i + 1]["start_idx"] if (i + 1 < total) else len(full_text)

            # Estimación rápida de páginas físicas para la interfaz
            start_page = PAGINAS_PRELIMINARES + full_text[:start].count('\n\n') // 20 + 1
            end_page = PAGINAS_PRELIMINARES + full_text[:end].count('\n\n') // 20 + 1

            resultado.append({
                "chapter_number": pos["numero"],
                "title": pos["titulo"],
                "start_page": max(1, start_page),
                "end_page": max(start_page, end_page),
                "start_idx": start,
                "end_idx": end,
                "content": ""  # Mantenemos ligero el objeto inicial
            })

        return resultado

    def get_chapter_content_by_pos(self, start_idx: int, end_idx: int) -> str:
        """
        Extrae el contenido exacto [XX : YX] de forma instantánea al hacer clic
        """
        PAGINAS_PRELIMINARES = min(15, len(self.doc))
        full_text = "\n".join(
            self.doc[p].get_text("text") for p in range(PAGINAS_PRELIMINARES, len(self.doc))
        )
        return full_text[start_idx:end_idx].strip()

    def _extraer_esqueleto_gemini(self) -> EsqueletoLibro:
        """Obtiene la lista ordenada de marcadores/capítulos desde los preliminares"""
        texto_preliminares = ""
        paginas_analizar = min(15, len(self.doc))
        for i in range(paginas_analizar):
            texto_preliminares += f"\n--- PÁGINA {i + 1} ---\n" + self.doc[i].get_text("text")

        prompt = f"""
        Analiza el texto de los preliminares de este libro y extrae el Índice / Tabla de Contenido.
        Extrae el identificador/número exacto del capítulo (ejemplo: '1', '2.5', '3.1.2') y su título.

        Texto preliminar:
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
            print(f"❌ Error en Gemini: {e}")
            return EsqueletoLibro(estructura=[])
        