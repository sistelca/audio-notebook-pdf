import os
from google import genai
from google.genai import types

class ChapterQAEngine:
    def __init__(self):
        # Toma la clave de API desde las variables de entorno de Docker
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY no está configurada en las variables de entorno.")
        
        self.client = genai.Client(api_key=api_key)

    def ask_chapter(self, chapter_title, chapter_text, question):
        """Envía el texto del capítulo activo como contexto exclusivo al modelo Gemini."""
        system_instruction = (
            "Eres un tutor académico experto y un asistente de estudio personalizado. "
            "Tu objetivo es ayudar al usuario a comprender y profundizar en el capítulo que está escuchando. "
            "Responde a las preguntas utilizando EXCLUSIVAMENTE la información del texto del capítulo proporcionado. "
            "Si la respuesta no se encuentra en el texto, indícalo amablemente sin inventar datos. "
            "Mantén un tono didáctico, claro y estructurado."
        )

        prompt = f"""
--- TEXTO DEL CAPÍTULO ({chapter_title}) ---
{chapter_text}

--- PREGUNTA DEL ESTUDIANTE ---
{question}
"""

        response = self.client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.3, # Broma/Creatividad baja para máxima fidelidad al texto
            ),
        )

        return response.text
    