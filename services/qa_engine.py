import os
import re
from google import genai
from google.genai import types

class ChapterQAEngine:
    def __init__(self):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY no está configurada en las variables de entorno.")
        
        self.client = genai.Client(api_key=api_key)

    def _clean_markdown_for_speech(self, text):
        """Elimina completamente cualquier caracter o formato Markdown para síntesis de voz limpia."""
        if not text:
            return ""

        # 1. Eliminar encabezados tipo #, ##, ###
        text = re.sub(r'#+\s*', '', text)
        
        # 2. Eliminar negritas y cursivas (**texto**, *texto*, __texto__, _texto_)
        text = re.sub(r'\*{1,3}(.*?)\*{1,3}', r'\1', text)
        text = re.sub(r'_{1,3}(.*?)_{1,3}', r'\1', text)
        
        # 3. Eliminar viñetas de listas (* item, - item, + item)
        text = re.sub(r'^\s*[\*\-\+]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'\n\s*[\*\-\+]\s+', '\n', text)

        # 4. Convertir listas numeradas (1. Item) en oraciones fluidas
        text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)

        # 5. Eliminar tildes invertidas / bloques de código (`código`)
        text = re.sub(r'`{1,3}(.*?)`{1,3}', r'\1', text)

        # 6. Eliminar barras de tablas o caracteres de formato
        text = text.replace('|', ', ')

        # 7. Normalizar espacios múltiples y saltos de línea
        text = re.sub(r'\n+', '. ', text)
        text = re.sub(r'\s+', ' ', text)

        return text.strip()

    def ask_chapter(self, chapter_title, chapter_text, question):
        """Envía la pregunta a Gemini y retorna un texto adaptado para voz."""
        system_instruction = (
            "Eres un tutor académico en formato de audio. "
            "Responde a la pregunta usando EXCLUSIVAMENTE el contenido del capítulo proporcionado. "
            "Redacta en un tono didáctico, fluido y continuo, utilizando conectores del lenguaje "
            "(como 'en primer lugar', 'por otra parte', 'en conclusión'). "
            "No uses listas, no uses saludos de cortesía ni símbolos de formato."
        )

        prompt = f"""
                Capítulo: {chapter_title}

                Contenido:
                {chapter_text}

                Pregunta:
                {question}
                """

        response = self.client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
            ),
        )

        # Aplicar la limpieza estricta en el servidor
        return self._clean_markdown_for_speech(response.text)
    