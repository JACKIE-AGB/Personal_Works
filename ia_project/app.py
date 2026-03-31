import gradio as gr
import requests
import os

API_URL = "http://localhost:8000"  # BUG CORREGIDO: era "https//"


# ─────────────────────────────────────────────
# FUNCIONES DE API
# ─────────────────────────────────────────────

def subir_pdf(pdf_file):
    """Sube un archivo PDF/TXT/MD desde la interfaz."""
    if pdf_file is None:
        return "⚠️ No se seleccionó ningún archivo."
    try:
        with open(pdf_file, "rb") as f:
            nombre = os.path.basename(pdf_file)
            r = requests.post(
                f"{API_URL}/upload_pdf",
                files={"file": (nombre, f)},
                timeout=30,
            )
        data = r.json()
        if r.status_code == 200:
            preview = data.get("preview", "")
            chars = data.get("caracteres", 0)
            return f"✅ {data['status']}\n📊 {chars} caracteres extraídos\n\n📄 Vista previa:\n{preview}"
        return f"❌ Error: {data.get('detail', r.text)}"
    except Exception as e:
        return f"❌ Error de conexión: {e}"


def buscar_en_carpeta(carpeta: str, nombre_busqueda: str, ruta_relativa: str):
    """
    Busca archivos en una carpeta del servidor.
    - carpeta:         Ruta de la carpeta, ej: /home/usuario/documentos
    - nombre_busqueda: Texto en el nombre del archivo (opcional)
    - ruta_relativa:   Ruta exacta dentro de la carpeta, ej: Proyectos/informe.pdf
    """
    if not carpeta.strip():
        return "⚠️ Escribe la ruta de una carpeta.", gr.update(choices=[], value=None)

    payload = {"carpeta": carpeta.strip()}
    if nombre_busqueda.strip():
        payload["nombre_busqueda"] = nombre_busqueda.strip()
    if ruta_relativa.strip():
        payload["ruta_relativa"] = ruta_relativa.strip()

    try:
        r = requests.post(f"{API_URL}/buscar_en_carpeta", json=payload, timeout=10)
        data = r.json()
        if r.status_code != 200:
            return f"❌ Error: {data.get('detail', r.text)}", gr.update(choices=[], value=None)

        archivos = data.get("archivos", [])
        total = data.get("total_encontrados", 0)

        if total == 0:
            return "⚠️ No se encontraron archivos.", gr.update(choices=[], value=None)

        # Opciones para el dropdown: "nombre (ruta_relativa)"
        opciones = [
            f"{a['nombre']}  →  {a.get('ruta_relativa', a['ruta_completa'])}"
            for a in archivos
        ]
        # Guardamos la ruta completa en un dict para recuperarla al seleccionar
        rutas_map = {
            f"{a['nombre']}  →  {a.get('ruta_relativa', a['ruta_completa'])}": a["ruta_completa"]
            for a in archivos
        }

        resumen = f"✅ {total} archivo(s) encontrado(s) en '{carpeta}'"
        return resumen, gr.update(choices=opciones, value=opciones[0] if opciones else None), rutas_map

    except Exception as e:
        return f"❌ Error de conexión: {e}", gr.update(choices=[], value=None), {}


def cargar_archivo_seleccionado(seleccion: str, rutas_map: dict):
    """Carga el archivo seleccionado del dropdown al contexto de la API."""
    if not seleccion:
        return "⚠️ Selecciona un archivo de la lista."
    ruta = rutas_map.get(seleccion, "")
    if not ruta:
        return "⚠️ No se pudo obtener la ruta del archivo."
    try:
        r = requests.post(
            f"{API_URL}/cargar_desde_ruta",
            json={"ruta_completa": ruta},
            timeout=30,
        )
        data = r.json()
        if r.status_code == 200:
            chars = data.get("caracteres", 0)
            preview = data.get("preview", "")
            return f"✅ {data['status']}\n📂 {ruta}\n📊 {chars} caracteres\n\n📄 Vista previa:\n{preview}"
        return f"❌ Error: {data.get('detail', r.text)}"
    except Exception as e:
        return f"❌ Error de conexión: {e}"


def hacer_pregunta(pregunta: str, max_tokens: int):
    """Envía una pregunta sobre el documento actualmente cargado."""
    if not pregunta.strip():
        return "⚠️ Escribe una pregunta."
    try:
        r = requests.post(
            f"{API_URL}/preguntar",
            json={"pregunta": pregunta.strip(), "max_tokens": int(max_tokens)},
            timeout=120,
        )
        data = r.json()
        if r.status_code == 200:
            archivo = data.get("archivo", "desconocido")
            return f"📂 Documento: {archivo}\n\n💬 {data['respuesta']}"
        return f"❌ Error: {data.get('detail', r.text)}"
    except Exception as e:
        return f"❌ Error de conexión: {e}"


def ver_estado():
    """Consulta el estado del servidor."""
    try:
        r = requests.get(f"{API_URL}/estado", timeout=5)
        d = r.json()
        return (
            f"🤖 Modelo: {d['modelo']}\n"
            f"📄 Archivo cargado: {d['archivo_cargado']}\n"
            f"📊 Caracteres en contexto: {d['caracteres_en_contexto']}"
        )
    except Exception as e:
        return f"❌ No se pudo conectar con la API: {e}"


# ─────────────────────────────────────────────
# INTERFAZ GRADIO
# ─────────────────────────────────────────────

with gr.Blocks(title="📄 PDF QA con IA", theme=gr.themes.Soft()) as demo:

    # Estado interno para guardar el mapa ruta
    rutas_state = gr.State({})

    gr.Markdown(
        """
        # 📄 Pregunta a tus documentos con IA
        Carga un PDF, TXT o Markdown — ya sea desde tu equipo o buscando en una carpeta del servidor —
        y haz preguntas sobre su contenido.
        """
    )

    # ── Sección de estado ──────────────────────────────
    with gr.Accordion("🔌 Estado del servidor", open=False):
        btn_estado = gr.Button("Consultar estado", variant="secondary")
        estado_txt = gr.Textbox(label="Estado", interactive=False, lines=3)
        btn_estado.click(ver_estado, outputs=estado_txt)

    gr.Markdown("---")

    # ── Tabs de carga ──────────────────────────────────
    with gr.Tabs():

        # TAB 1: Subir archivo directamente
        with gr.Tab("📂 Subir archivo"):
            gr.Markdown("Selecciona un archivo **PDF**, **TXT** o **MD** desde tu equipo.")
            archivo_input = gr.File(
                label="Archivo",
                file_types=[".pdf", ".txt", ".md"],
            )
            btn_subir = gr.Button("⬆️ Cargar archivo", variant="primary")
            estado_subida = gr.Textbox(label="Resultado", interactive=False, lines=5)
            btn_subir.click(subir_pdf, inputs=archivo_input, outputs=estado_subida)

        # TAB 2: Buscar en carpeta del servidor
        with gr.Tab("🗂️ Buscar en carpeta"):
            gr.Markdown(
                """
                Busca archivos en una carpeta del **servidor**.  
                Puedes buscar por nombre o indicar una ruta relativa como `Proyectos/2024/informe.pdf`.
                """
            )
            with gr.Row():
                carpeta_input = gr.Textbox(
                    label="📁 Ruta de la carpeta",
                    placeholder="/home/usuario/documentos",
                )
                nombre_input = gr.Textbox(
                    label="🔍 Buscar por nombre (opcional)",
                    placeholder="informe",
                )
            ruta_relativa_input = gr.Textbox(
                label="📌 Ruta relativa exacta (opcional)",
                placeholder="SubCarpeta/Documento.pdf",
            )
            btn_buscar = gr.Button("🔎 Buscar archivos", variant="primary")
            estado_busqueda = gr.Textbox(label="Resultado de búsqueda", interactive=False, lines=2)
            archivo_dropdown = gr.Dropdown(
                label="📋 Archivos encontrados — selecciona uno para cargarlo",
                choices=[],
                interactive=True,
            )
            btn_cargar_sel = gr.Button("📥 Cargar archivo seleccionado", variant="primary")
            estado_carga_sel = gr.Textbox(label="Resultado de carga", interactive=False, lines=5)

            btn_buscar.click(
                buscar_en_carpeta,
                inputs=[carpeta_input, nombre_input, ruta_relativa_input],
                outputs=[estado_busqueda, archivo_dropdown, rutas_state],
            )
            btn_cargar_sel.click(
                cargar_archivo_seleccionado,
                inputs=[archivo_dropdown, rutas_state],
                outputs=estado_carga_sel,
            )

    gr.Markdown("---")

    # ── Sección de preguntas ───────────────────────────
    gr.Markdown("## 💬 Haz preguntas sobre el documento cargado")
    with gr.Row():
        pregunta_input = gr.Textbox(
            label="Pregunta",
            placeholder="¿De qué trata el documento? ¿Cuáles son las conclusiones principales?",
            lines=2,
            scale=4,
        )
        max_tokens_slider = gr.Slider(
            minimum=128,
            maximum=1024,
            value=512,
            step=64,
            label="Longitud máxima de respuesta",
            scale=1,
        )
    btn_preguntar = gr.Button("🤖 Preguntar", variant="primary", size="lg")
    respuesta_output = gr.Textbox(label="Respuesta", lines=10, interactive=False)

    btn_preguntar.click(
        hacer_pregunta,
        inputs=[pregunta_input, max_tokens_slider],
        outputs=respuesta_output,
    )

demo.launch(server_name="0.0.0.0", server_port=7860)