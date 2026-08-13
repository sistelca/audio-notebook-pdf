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
            "Eres un tutor académico y asistente de estudio en formato de voz. "
            "Tu objetivo es responder a las preguntas del usuario utilizando EXCLUSIVAMENTE "
            "la información del capítulo proporcionado.\n\n"
            "REGLAS CRÍTICAS DE FORMATO PARA LECTURA POR VOZ (TEXT-TO-SPEECH):\n"
            "1. NO utilices ningun tipo de formato Markdown: NO uses asteriscos (*), almohadillas (#), "
            "negritas (**), cursivas, ni guiones de lista.\n"
            "2. NO uses tablas ni esquemas visuales. Traduce cualquier comparación o lista a párrafos "
            "narrativos continuos y bien estructurados.\n"
            "3. NO agregues saludos ni muletillas de cortesía (evita frases como '¡Claro!', 'Con gusto', 'A continuación te presento'). "
            "Comienza directamente con la respuesta.\n"
            "4. Utiliza únicamente texto plano. Separa las ideas principales con puntos seguidos o saltos de párrafo simples.\n"
            "5. Redacta con un lenguaje natural, continuo y conversacional, usando conectores gramaticales "
            "(como 'en primer lugar', 'por otro lado', 'en segundo lugar', 'en conclusión') para que la síntesis de voz "
            "suene fluida, pausada y agradable de escuchar."
        )

        prompt = f"""
                    Capítulo: {chapter_title}

                    Contenido del capítulo:
                    {chapter_text}

                    Pregunta del estudiante:
                    {question}
                """

        response = self.client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2, # Broma/Creatividad baja para máxima fidelidad al texto
            ),
        )

        return response.text
    