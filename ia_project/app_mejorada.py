import gradio as gr
import requests
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_URL = "http://localhost:8000"

# Funciones de API
def subir_pdf(pdf_file):
    """Sube un archivo PDF desde la interfaz"""
    if pdf_file is None:
        return "⚠️ No se seleccionó ningún archivo."
    
    try:
        with open(pdf_file, "rb") as f:
            nombre = os.path.basename(pdf_file)
            r = requests.post(
                f"{API_URL}/upload_pdf",
                files={"file": (nombre, f)},
                timeout=60
            )
        
        if r.status_code == 200:
            data = r.json()
            preview = data.get("preview", "")
            chars = data.get("caracteres", 0)
            return f"✅ {data['status']}\n📊 {chars} caracteres extraídos\n\n📄 Vista previa:\n{preview}"
        else:
            error = r.json().get('detail', r.text)
            return f"❌ Error: {error}"
            
    except requests.exceptions.ConnectionError:
        return "❌ No se pudo conectar con la API. Asegúrate de que api.py esté corriendo en el puerto 8000."
    except Exception as e:
        logger.error(f"Error al subir PDF: {e}")
        return f"❌ Error inesperado: {e}"

def cargar_desde_ruta(ruta_archivo):
    """Carga un archivo desde una ruta local"""
    if not ruta_archivo or not ruta_archivo.strip():
        return "⚠️ Ingresa la ruta del archivo PDF"
    
    if not ruta_archivo.lower().endswith('.pdf'):
        return "⚠️ El archivo debe tener extensión .pdf"
    
    try:
        r = requests.post(
            f"{API_URL}/cargar_desde_ruta",
            json={"ruta_completa": ruta_archivo.strip()},
            timeout=60
        )
        
        if r.status_code == 200:
            data = r.json()
            chars = data.get("caracteres", 0)
            preview = data.get("preview", "")
            return f"✅ {data['status']}\n📂 {ruta_archivo}\n📊 {chars} caracteres\n\n📄 Vista previa:\n{preview}"
        else:
            error = r.json().get('detail', r.text)
            return f"❌ Error: {error}"
            
    except requests.exceptions.ConnectionError:
        return "❌ No se pudo conectar con la API. Asegúrate de que api.py esté corriendo en el puerto 8000."
    except Exception as e:
        logger.error(f"Error al cargar desde ruta: {e}")
        return f"❌ Error: {e}"

def hacer_pregunta(pregunta, max_tokens):
    """Envía una pregunta y recibe la respuesta palabra por palabra (Streaming)"""
    if not pregunta or not pregunta.strip():
        yield "⚠️ Escribe una pregunta."
        return
    
    yield "⏳ Analizando documento y pensando la respuesta..."
    
    try:
        # Añadimos stream=True y aumentamos el timeout general a 5 minutos
        r = requests.post(
            f"{API_URL}/preguntar",
            json={"pregunta": pregunta.strip(), "max_tokens": int(max_tokens)},
            stream=True,
            timeout=300 
        )
        
        if r.status_code == 200:
            respuesta_completa = ""
            # Iteramos sobre los pedacitos de texto que envía la API
            for chunk in r.iter_content(chunk_size=None, decode_unicode=True):
                if chunk:
                    respuesta_completa += chunk
                    yield f"💬 {respuesta_completa}"
        else:
            # Manejo de error si la respuesta no fue 200 OK
            try:
                error = r.json().get('detail', r.text)
            except:
                error = r.text
            yield f"❌ Error: {error}"
            
    except requests.exceptions.ConnectionError:
        yield "❌ No se pudo conectar con la API. Asegúrate de que api.py esté corriendo en el puerto 8000."
    except requests.exceptions.Timeout:
        yield "❌ La pregunta tomó demasiado tiempo. Intenta con un texto más corto o reduce la longitud máxima."
    except Exception as e:
        logger.error(f"Error al hacer pregunta: {e}")
        yield f"❌ Error inesperado: {e}"

def ver_estado():
    """Consulta el estado del servidor"""
    try:
        r = requests.get(f"{API_URL}/estado", timeout=10)
        if r.status_code == 200:
            d = r.json()
            modelo_status = "✅ Cargado" if d.get('modelo_cargado', False) else "❌ No disponible"
            return (
                f"🤖 Modelo: {d['modelo']}\n"
                f"📊 Estado del modelo: {modelo_status}\n"
                f"📄 Archivo cargado: {os.path.basename(d['archivo_cargado']) if d['archivo_cargado'] != 'Ninguno' else 'Ninguno'}\n"
                f"📊 Caracteres en contexto: {d['caracteres_en_contexto']}\n"
                f"💻 Dispositivo: {d['dispositivo']}"
            )
        else:
            return f"❌ Error: Estado {r.status_code}"
    except requests.exceptions.ConnectionError:
        return "❌ No se pudo conectar con la API. Asegúrate de que api.py esté corriendo:\n  python api.py"
    except Exception as e:
        return f"❌ Error: {e}"

# Crear interfaz Gradio
with gr.Blocks(title="📄 PDF QA con IA", theme=gr.themes.Soft()) as demo:
    gr.Markdown(
        """
        # 📄 Pregunta a tus documentos PDF con IA
        Sube un archivo PDF o ingresa la ruta local y haz preguntas sobre su contenido.
        """
    )
    
    # Estado del servidor
    with gr.Accordion("🔌 Estado del servidor", open=False):
        btn_estado = gr.Button("Consultar estado", variant="secondary")
        estado_txt = gr.Textbox(label="Estado", interactive=False, lines=5)
        btn_estado.click(ver_estado, outputs=estado_txt)
    
    gr.Markdown("---")
    
    with gr.Tabs():
        # Pestaña de subida de archivo
        with gr.Tab("📂 Subir archivo"):
            gr.Markdown("Selecciona un archivo **PDF** desde tu computadora.")
            archivo_input = gr.File(
                label="Archivo PDF",
                file_types=[".pdf"],
                type="filepath"
            )
            btn_subir = gr.Button("⬆️ Cargar archivo", variant="primary")
            estado_subida = gr.Textbox(label="Resultado", interactive=False, lines=8)
            btn_subir.click(subir_pdf, inputs=archivo_input, outputs=estado_subida)
        
        # Pestaña de ruta local
        with gr.Tab("📁 Ruta local"):
            gr.Markdown("Ingresa la **ruta completa** de un archivo PDF en el servidor.")
            ruta_input = gr.Textbox(
                label="Ruta del archivo PDF",
                placeholder="/home/usuario/documentos/mi_archivo.pdf",
                lines=1
            )
            btn_cargar_ruta = gr.Button("📥 Cargar desde ruta", variant="primary")
            estado_ruta = gr.Textbox(label="Resultado", interactive=False, lines=8)
            btn_cargar_ruta.click(cargar_desde_ruta, inputs=ruta_input, outputs=estado_ruta)
    
    gr.Markdown("---")
    
 # Sección de preguntas
    gr.Markdown("## 💬 Haz preguntas sobre el documento cargado")
    
    with gr.Row():
        pregunta_input = gr.Textbox(
            label="Pregunta",
            placeholder="¿De qué trata el documento? ¿Cuáles son las conclusiones principales?",
            lines=3,
            scale=4
        )
        max_tokens_slider = gr.Slider(
            minimum=128,
            maximum=1024,
            value=256,
            step=64,
            label="Longitud máxima de respuesta (menor = mas rapida)",
            scale=1
        )
    
    # AÑADIDO: Fila con botón de preguntar y botón de cancelar
    with gr.Row():
        btn_preguntar = gr.Button("🤖 Preguntar", variant="primary", scale=3)
        btn_cancelar = gr.Button("🛑 Cancelar", variant="stop", scale=1)
        
    respuesta_output = gr.Textbox(label="Respuesta", lines=12, interactive=False)
    
    # AÑADIDO: Guardamos el evento de la pregunta en una variable
    evento_pregunta = btn_preguntar.click(
        hacer_pregunta,
        inputs=[pregunta_input, max_tokens_slider],
        outputs=respuesta_output
    )
    
    # AÑADIDO: El botón cancelar interrumpe específicamente ese evento
    btn_cancelar.click(
        fn=None, 
        inputs=None, 
        outputs=None, 
        cancels=[evento_pregunta]
    )
    
    gr.Markdown("---")
    gr.Markdown("💡 **Consejos:**")
    gr.Markdown("- Asegúrate de que el servidor API esté corriendo antes de usar la interfaz")
    gr.Markdown("- La primera pregunta puede tardar más debido a la carga del modelo")
    gr.Markdown("- Para mejores resultados, haz preguntas específicas sobre el contenido del PDF")

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False
    )