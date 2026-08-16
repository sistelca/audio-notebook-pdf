import json
import os
import re
from typing import List
from dotenv import load_dotenv  # Importación agregada
from google import genai
from google.genai import types
import pymupdf
from pydantic import BaseModel, Field
from services.utils.logger import get_logger


logger = get_logger(__name__)

def es_pagina_candidata_indice(texto_pagina: str) -> bool:
    """
    Evalúa si el texto de una página coincide con la estructura de un índice.
    """
    # Patrón Regex:
    # ^\s* -> Inicio de línea (ignorando espacios iniciales)
    # [^\n\r\d]+ -> Título (al menos un carácter que no sea salto de línea ni dígito inicial)
    # (?:[\.\-\_\s]{2,}|\t+) -> Al menos 2 caracteres de guía (puntos, guiones, guiones bajos, espacios) o una tabulación
    # \d+\s*$ -> Termina en uno o más dígitos (número de página)
    patron_indice = re.compile(
        r'^\s*[^\n\r\d]+(?:[\.\-\_\s]{2,}|\t+)\d+\s*$', 
        re.MULTILINE
    )
    
    # Buscamos cuántas líneas de la página cumplen con este patrón
    lineas_coincidentes = patron_indice.findall(texto_pagina)
    
    # Encabezados típicos
    tiene_encabezado = bool(re.search(r'\b(índice|tabla de contenidos|contents|index)\b', texto_pagina, re.IGNORECASE))
    
    # Si tiene al menos 3 líneas de estructura de índice O (1 línea + encabezado claro)
    if len(lineas_coincidentes) >= 3 or (len(lineas_coincidentes) >= 1 and tiene_encabezado):
        return True
        
    return False

# ------------------------------------------------------------------
# 1. Esquema Pydantic para la respuesta de Gemini
# ------------------------------------------------------------------

class EntradaIndice(BaseModel):
    nivel: str
    numero: str | None
    titulo: str
    pagina_libro: str

class IndiceEstructurado(BaseModel):
    elementos: List[EntradaIndice] = Field(
        description="Lista ordenada con todas las entradas desglosadas del índice."
    )
    
class EvaluacionPaginas(BaseModel):
    indices_confirmados: list[int] = Field(
        description="Lista con los id_local de las páginas que SÍ son parte del índice general"
    )
    
class PaginaIndice(BaseModel):
    numero_de_pagina: int
    razon: str

class EsqueletoLibro(BaseModel):
    paginas_indice: list[PaginaIndice] = Field(default_factory=list)
    texto_extraido_indice: str = ""
    # Si quieres mantener 'estructura' como opcional:
    estructura: list[dict] = Field(default_factory=list)

# ------------------------------------------------------------------
# 2. Clase Extractora con Delimitación Exacta de Texto
# ------------------------------------------------------------------
class PDFChapterExtractor:

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.doc = pymupdf.open(pdf_path)

        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")

        self.client = genai.Client(api_key=api_key)


    def get_chapters(self) -> IndiceEstructurado:
        # 1. Obtener el esqueleto con las páginas y el texto del índice
        esqueleto = self._extraer_esqueleto_gemini()

        # CORRECCIÓN: Validar 'texto_extraido_indice' en lugar de 'estructura'
        if not esqueleto or not esqueleto.texto_extraido_indice:
            return IndiceEstructurado(elementos=[])

        prompt = f"a partir de esta cadena de texto, genera una tabla de indices pero como json: {esqueleto.texto_extraido_indice}"

        try:
            # 4. Llamada ultrarrápida a Gemini
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',

                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=IndiceEstructurado,
                    temperature=0.0
                ),
            )
            
            # Parse del resultado rápido (un arreglo de ints)
            resultado: IndiceEstructurado = response.parsed
            capitulosL = resultado.model_dump_json(indent=2)
            capitulos = json.loads(capitulosL).get('elementos')
            for id_, x in enumerate(capitulos):
                x['id'] = id_
            return json.dumps(capitulos)
        
        except Exception as e:
            logger.exception(f"❌ Error en Gemini: {e}")
            return None

    def _extraer_esqueleto_gemini(self) -> EsqueletoLibro:
        """Obtiene la lista ordenada de marcadores/capítulos desde los preliminares"""
        
        # 1. Optimización Python: Extraer texto 1 sola vez por página
        limite = min(50, len(self.doc))
        candidatas = []
        
        for p in range(limite):
            texto = self.doc[p].get_text("text")
            if es_pagina_candidata_indice(texto):
                candidatas.append({
                    "id_local": len(candidatas),
                    "numero_pagina_pdf": p + 1,  # Número real de página en el PDF
                    "texto": texto
                })
    
        # Si el filtro regex no encontró nada, salimos de inmediato
        if not candidatas:
            return EsqueletoLibro(paginas_indice=[], texto_extraido_indice="")
    
        # 2. Preparamos una lista liviana para el prompt
        datos_entrada = [
            {"id_local": c["id_local"], "pagina_pdf": c["numero_pagina_pdf"], "texto": c["texto"]}
            for c in candidatas
        ]
    
        # 3. Prompt minimalista (Aprovechando que response_schema ya define la estructura)
        prompt = f"""
        Analiza estas páginas candidatas extraídas de los preliminares de un libro.
        Identifica cuáles forman parte del ÍNDICE GENERAL (Tabla de contenidos).
        Ignora índices analíticos, de materias o alfabéticos al final del libro.
    
        Páginas candidatas:
        {json.dumps(datos_entrada, ensure_ascii=False)}
        """
    
        try:
            # 4. Llamada ultrarrápida a Gemini
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',

                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=EvaluacionPaginas,
                    temperature=0.0
                ),
            )
            
            # Parse del resultado rápido (un arreglo de ints)
            resultado: EvaluacionPaginas = response.parsed
            ids_validos = set(resultado.indices_confirmados)
    
            # 5. Reconstrucción instantánea en Python
            paginas_finales = []
            textos_filtrados = []
    
            for c in candidatas:
                if c["id_local"] in ids_validos:
                    paginas_finales.append({
                        "numero_de_pagina": c["numero_pagina_pdf"],
                        "razon": "Confirmado por Gemini como parte del índice"
                    })
                    textos_filtrados.append(c["texto"])
    
            return EsqueletoLibro(
                paginas_indice=paginas_finales,
                texto_extraido_indice="\n\n".join(textos_filtrados)
            )
    
        except Exception as e:
            logger.exception(f"❌ Error en Gemini: {e}")
            return EsqueletoLibro(paginas_indice=[], texto_extraido_indice="")

    def get_chapter(self, chapters, chapter_id):
        pos, chapter = next((i, ch) for i, ch in enumerate(chapters) if ch['id']==chapter_id)

        try:
            realpag_in, pagtxt = next(
                (
                    (i, x.get_text("text")) for i, x in enumerate(self.doc) if (chapter.get('titulo') in x.get_text("text") and 
                                                        not es_pagina_candidata_indice(x.get_text("text")))
                ), None
            )
            pagtxt = [pagtxt[pagtxt.find(chapter['titulo']):]]

            if pos < len(chapters) - 1:
                next_chapter = chapters[pos + 1]
                realpag_fn , pagfntxt = next(
                    (
                        (i, x.get_text("text")) for i, x in enumerate(self.doc) if (next_chapter.get('titulo') in x.get_text("text") and 
                                                            not es_pagina_candidata_indice(x.get_text("text")))
                    ), None
                )            
                pagfntxt = [pagfntxt[:pagfntxt.find(next_chapter['titulo'])]]

                sub_doc = pagtxt + self.doc[realpag_in + 1:realpag_fn - 1] + pagfntxt
            else:
                sub_doc = pagtxt + self.doc[realpag_in + 1:]

            return {'id': chapter_id, 'title': chapter.get('titulo'), 'paragraphs': sub_doc}

        except Exception as e:
            logger.exception(f"❌ Error en get_chapter: {e}")
            return None
        
