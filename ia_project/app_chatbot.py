import gradio as gr
import requests

API_URL = "http://localhost:8000"


# ─────────────────────────────────────────────
# ESTADO DE CONEXIÓN
# ─────────────────────────────────────────────

def verificar_backend() -> str:
    try:
        r = requests.get(f"{API_URL}/status", timeout=5)
        r.raise_for_status()
        data = r.json()
        if data.get("documento_activo"):
            return f"✅ Conectado | 📄 '{data['documento_activo']}' ({data['paginas']} pág.)"
        return "✅ Conectado | Sin documento cargado"
    except Exception:
        return "❌ Backend no disponible — ¿está corriendo api_conversacional.py?"


# ─────────────────────────────────────────────
# FUNCIÓN PRINCIPAL
# ─────────────────────────────────────────────

def responder(message, history):
    """
    Generador compatible con Gradio 4.x multimodal.

    CORRECCIONES:
    - respuesta_acumulada empieza con la info del PDF, el streaming del
      modelo se AÑADE en lugar de reemplazarla (ese era el bug principal).
    - El generador termina con return explícito en todos los caminos,
      así Gradio desbloquea el input siempre.
    - Se eliminó 'every' del Textbox de estado (incompatible con Gradio antiguo).
    """
    user_text = (
        message.get("text", "").strip()
        if isinstance(message, dict)
        else str(message).strip()
    )
    files = message.get("files", []) if isinstance(message, dict) else []

    if not user_text and not files:
        yield "Por favor escribe algo o sube un archivo PDF."
        return

    # ── 1. Subir archivos ──────────────────────────────────────────
    # respuesta_acumulada acumula TODO el texto del chat bubble.
    # Inicializarla aquí y luego añadir el streaming del modelo encima
    # evita que el texto de confirmación del PDF desaparezca.
    respuesta_acumulada = ""

    if files:
        for ruta_archivo in files:
            nombre = (
                ruta_archivo.split("/")[-1]
                if isinstance(ruta_archivo, str)
                else "archivo.pdf"
            )
            try:
                respuesta_acumulada = f"⏳ Procesando **{nombre}**..."
                yield respuesta_acumulada

                with open(ruta_archivo, "rb") as f:
                    resp = requests.post(
                        f"{API_URL}/upload",
                        files={"file": (nombre, f, "application/pdf")},
                        timeout=90,
                    )
                    resp.raise_for_status()
                    data = resp.json()

                info = (
                    f"✅ **{data.get('archivo', nombre)}** cargado\n"
                    f"- Páginas: {data.get('paginas', '?')}\n"
                    f"- Caracteres extraídos: {data.get('chars', '?'):,}\n"
                    f"- Tablas detectadas: {'Sí' if data.get('tablas') else 'No'}"
                )
                if data.get("advertencias"):
                    info += "\n\n" + "\n".join(data["advertencias"])

                # Sin pregunta → solo mostrar confirmación y terminar limpio
                if not user_text:
                    yield info
                    return

                # Con pregunta → el prefijo del PDF + separador queda en el acumulador
                respuesta_acumulada = info + "\n\n---\n\n"
                yield respuesta_acumulada

            except requests.HTTPError as e:
                try:
                    detalle = e.response.json().get("detail", str(e))
                except Exception:
                    detalle = str(e)
                yield f"❌ Error al subir **{nombre}**: {detalle}"
                return
            except Exception as e:
                yield f"❌ Error inesperado al subir **{nombre}**: {e}"
                return

    if not user_text:
        return

    # ── 2. Construir historial limpio ──────────────────────────────
    messages = []
    for entrada in history:
        if isinstance(entrada, (list, tuple)) and len(entrada) == 2:
            human, asistente = entrada
            if isinstance(human, dict):
                human = human.get("text", "")
            if human:
                messages.append({"role": "user", "content": str(human)})
            if asistente:
                # Quitar el prefijo de confirmación de PDF del historial
                # para no contaminar el contexto del modelo
                texto_asistente = str(asistente)
                if "---\n\n" in texto_asistente:
                    texto_asistente = texto_asistente.split("---\n\n", 1)[-1].strip()
                if texto_asistente:
                    messages.append({"role": "assistant", "content": texto_asistente})
        elif isinstance(entrada, dict):
            messages.append({
                "role": entrada.get("role", "user"),
                "content": entrada.get("content", ""),
            })

    messages.append({"role": "user", "content": user_text})

    # ── 3. Streaming del modelo ────────────────────────────────────
    try:
        with requests.post(
            f"{API_URL}/chat",
            json={"messages": messages, "max_tokens": 768},
            stream=True,
            timeout=180,
        ) as resp:
            resp.raise_for_status()
            for chunk in resp.iter_content(chunk_size=None, decode_unicode=True):
                if chunk:
                    respuesta_acumulada += chunk   # se AÑADE al prefijo del PDF
                    yield respuesta_acumulada

    except requests.exceptions.ConnectionError:
        yield (
            respuesta_acumulada
            + "\n\n❌ Sin conexión al backend. "
            "Verifica que `api_conversacional.py` esté corriendo en el puerto 8000."
        )
    except requests.exceptions.Timeout:
        yield respuesta_acumulada + "\n\n⏱️ El modelo tardó demasiado. Intenta de nuevo."
    except Exception as e:
        yield respuesta_acumulada + f"\n\n❌ Error: {e}"


def limpiar_documento():
    try:
        requests.delete(f"{API_URL}/documento", timeout=5)
    except Exception:
        pass
    return verificar_backend()


# ─────────────────────────────────────────────
# INTERFAZ GRADIO
# ─────────────────────────────────────────────

tema = gr.themes.Soft(
    primary_hue="slate",
    secondary_hue="blue",
    radius_size="lg",
).set(
    body_background_fill="*neutral_50",
    block_label_text_size="*text_sm",
    input_background_fill="*white",
)

with gr.Blocks(theme=tema, title="Asistente PDF") as demo:

    gr.Markdown(
        """
        <center>
        <h1>📄 Asistente de Documentos PDF</h1>
        <p style="color: gray;">Sube un PDF y haz cualquier pregunta sobre su contenido</p>
        </center>
        """
    )

    # ── Barra de estado ────────────────────────────────────────────
    # value=verificar_backend() → llamada directa (no referencia a función)
    # Evita el bug de bloqueo de UI en versiones antiguas de Gradio.
    with gr.Row():
        estado_label = gr.Textbox(
            value=verificar_backend(),
            label="Estado del backend",
            interactive=False,
            scale=4,
        )
        with gr.Column(scale=1, min_width=160):
            btn_refrescar = gr.Button("🔄 Actualizar estado", variant="secondary")
            btn_limpiar   = gr.Button("🗑️ Quitar documento",  variant="secondary")

    # ── Chat ───────────────────────────────────────────────────────
    chat = gr.ChatInterface(
        fn=responder,
        multimodal=True,
        textbox=gr.MultimodalTextbox(
            placeholder="Sube un PDF con 📎 o escribe tu pregunta...",
            show_label=False,
            file_types=[".pdf"],
        ),
    )

    btn_refrescar.click(fn=verificar_backend, outputs=estado_label)
    btn_limpiar.click(fn=limpiar_documento,   outputs=estado_label)

    gr.Markdown(
        """
        ---
        **Consejos:**
        - Puedes subir el PDF y escribir tu pregunta en el mismo mensaje.
        - Para mejores resultados usa PDFs con texto seleccionable (no escaneos).
        - El modelo recuerda el documento durante toda la conversación.
        - Usa **Quitar documento** para cargar un PDF diferente.
        """
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, show_error=True)