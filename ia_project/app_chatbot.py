import gradio as gr
import requests
import json

API_URL = "http://localhost:8000"

def responder(message, history):
    # 'message' es un dict con {'text': '...', 'files': [...]}
    user_text = message["text"]
    files = message["files"]
    
    # 1. Si hay archivos, subirlos primero
    if files:
        for f in files:
            with open(f, "rb") as file_data:
                requests.post(f"{API_URL}/upload", files={"file": file_data})
    
    # 2. Preparar historial para la API
    messages = []
    for human, ai in history:
        messages.append({"role": "user", "content": human})
        messages.append({"role": "assistant", "content": ai})
    messages.append({"role": "user", "content": user_text})

    # 3. Llamada streaming a la API
    response = requests.post(
        f"{API_URL}/chat",
        json={"messages": messages, "max_tokens": 512},
        stream=True
    )
    
    partial_text = ""
    for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
        if chunk:
            partial_text += chunk
            yield partial_text

# Configuración Estética (Minimalista)
theme = gr.themes.Soft(
    primary_hue="slate",
    radius_size="lg",
).set(
    body_background_fill="*neutral_50",
    block_label_text_size="*text_sm",
    input_background_fill="*white",
)

with gr.Blocks(theme=theme, title="AI Chatbot") as demo:
    gr.Markdown("<center><h1>✨ Asistente Inteligente</h1></center>")
    
    chat = gr.ChatInterface(
        fn=responder,
        multimodal=True, # Permite subir archivos directamente en el clip de la barra
        textbox=gr.MultimodalTextbox(
            placeholder="Pregunta cualquier cosa o sube un PDF...",
            show_label=False,
            container=True,
        ),
        # stop_btn="🛑 Detener",
        # submit_btn="🚀",
        # retry_btn="🔄 Reintentar",
        # undo_btn="↩️ Deshacer",
        # clear_btn="🗑️ Limpiar",
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)