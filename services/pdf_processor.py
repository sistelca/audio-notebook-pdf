import pymupdf
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
# 2. Clase Extractora Refactorizada con Gemini + PyMuPDF
# ------------------------------------------------------------------
class PDFChapterExtractor:
    def __init__(self, pdf_path: str, client):
        self.pdf_path = pdf_path
        self.doc = pymupdf.open(pdf_path)
        # Inicializa cliente de Gemini usando GEMINI_API_KEY del entorno
        self.client = client

    def get_chapters(self) -> list[dict]:
        """
        Extrae la estructura usando Gemini, calcula rangos de páginas reales 
        y extrae el contenido de cada capítulo para la BD.
        """
        # Paso 1: Consultar a Gemini el índice impreso en las primeras páginas
        esqueleto = self._extraer_esqueleto_gemini()
        if not esqueleto or not esqueleto.estructura:
            return []

        # Paso 2: Filtrar solo capítulos/partes principales y buscar sus páginas físicas
        capitulos_mapeados = self._mapear_paginas_fisicas(esqueleto)
        
        # Paso 3: Calcular rangos (start_page, end_page) y extraer el texto
        resultado = []
        total_caps = len(capitulos_mapeados)

        for i, cap in enumerate(capitulos_mapeados):
            start_page = cap["pagina_fisica_real"]
            
            # La página final es la página inicial del siguiente capítulo menos 1, 
            # o la última página del documento si es el último capítulo.
            if i + 1 < total_caps:
                end_page = capitulos_mapeados[i + 1]["pagina_fisica_real"] - 1
            else:
                end_page = len(self.doc)

            # Asegurar rangos válidos
            if end_page < start_page:
                end_page = start_page

            # Extraer el texto completo de este rango de páginas
            content = self._extraer_texto_rango(start_page, end_page)

            resultado.append({
                "chapter_number": cap["numero"],
                "title": cap["titulo"],
                "start_page": start_page,
                "end_page": end_page,
                "content": content
            })

        return resultado

    def _extraer_esqueleto_gemini(self) -> EsqueletoLibro:
        """Extrae el texto preliminar y le pide el índice estructurado a Gemini"""
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

    def _mapear_paginas_fisicas(self, esqueleto: EsqueletoLibro) -> list[dict]:
        """Usa PyMuPDF para encontrar en qué página física real comienza cada capítulo"""
        capitulos = []
        idx = 1

        for item in esqueleto.estructura:
            titulo_clean = item.titulo.lower().strip()
            pagina_fisica = None

            # Buscar la primera coincidencia del título en todo el documento
            for page_index in range(len(self.doc)):
                texto_pag = self.doc[page_index].get_text("text").lower()
                if titulo_clean in texto_pag:
                    pagina_fisica = page_index + 1  # Base 1
                    break

            # Si se encontró la página, lo agregamos como capítulo válido
            if pagina_fisica:
                num_cap = item.numero if item.numero else str(idx)
                capitulos.append({
                    "numero": num_cap,
                    "titulo": item.titulo,
                    "pagina_fisica_real": pagina_fisica
                })
                idx += 1

        return capitulos

    def _extraer_texto_rango(self, start_page: int, end_page: int) -> str:
        """Extrae todo el texto comprendido entre dos páginas (base 1)"""
        texto = ""
        for p in range(start_page - 1, end_page):
            if p < len(self.doc):
                texto += self.doc[p].get_text("text") + "\n\n"
        return texto.strip()
    