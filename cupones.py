import os
import PIL.Image
import json
import re
from google import genai

MODEL_NAME = "gemini-1.5-flash"

def extraer_datos_cupon(ruta_imagen):
    """
    Usa la IA de Gemini para leer el ticket de descuento del supermercado,
    extrayendo las condiciones, producto, caducidad y código de barras.
    """
    try:
        api_key = os.environ.get("API_KEY")
        if not api_key: return None

        client = genai.Client(api_key=api_key)
        img = PIL.Image.open(ruta_imagen)

        prompt = """
        Estás analizando la foto de un CUPÓN / VALE DE DESCUENTO o TICKET de un supermercado en España 
        (Carrefour, Dia, Mercadona, Lidl, Eroski, Alcampo, El Corte Inglés, Consum, etc).

        Tu misión es extraer la información clave para digitalizarlo.

        INSTRUCCIONES CRÍTICAS:
        1. Identifica el NOMBRE DEL SUPERMERCADO (ej: 'Carrefour', 'Dia', 'Lidl').
        2. Extrae el TÍTULO / PRODUCTO del descuento (ej: '2€ de descuento en Detergente', '-20% en Aceite').
        3. Extrae el IMPORTE numérico del ahorro estimado (ej: si es '3€', pon 3.0; si es '1,50€', pon 1.5; si es porcentaje pon 0).
        4. Extrae las CONDICIONES o letra pequeña (ej: 'Por compras superiores a 15€', 'Válido en 2ª unidad').
        5. Extrae la FECHA DE CADUCIDAD en formato DD/MM/YYYY exacto. Si no tiene, pon 'Sin fecha'.
        6. Extrae los números del CÓDIGO DE BARRAS o cupón (generalmente entre 8 y 18 dígitos impresos bajo las barras).

        DEVUELVE ÚNICAMENTE UN OBJETO JSON VÁLIDO (sin markdown, sin explicaciones):
        {
            "supermercado": "Carrefour",
            "titulo_descuento": "3€ de descuento en Pescadería",
            "importe_descuento": 3.0,
            "condiciones": "Gasto mínimo de 12€ en pescadería",
            "fecha_caducidad": "28/08/2026",
            "codigo_barras": "8437012398412"
        }
        """

        print("🤖 CuponIA Vision analizando vale de descuento...")
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[prompt, img]
        )

        texto_crudo = response.text.strip()
        texto_crudo = re.sub(r'^```json\s*', '', texto_crudo, flags=re.MULTILINE)
        texto_crudo = re.sub(r'^```\s*', '', texto_crudo, flags=re.MULTILINE)
        texto_crudo = re.sub(r'```$', '', texto_crudo, flags=re.MULTILINE).strip()

        return json.loads(texto_crudo)

    except Exception as e:
        print(f"❌ Error Visión CuponIA: {e}")
        return None