import gradio as gr
import requests

API_URL = "https//localhost:8000"

def subir_pdf(pdf):
    with open(pdf, "rb") as f:
        r = requests.post(
            f"{API_URL}/upload_pdf",
            files={"file": f}
        )
    return r.json()["status"]

def hacer_pregunta(pregunta):
    r = requests.post(
        f"{API_URL}/preguntar",
        params={"pregunta": pregunta}
    )
    return r.json()["respuesta"]

with gr.Blocks(title="Preguntas sobre PDF con IA") as demo:
    gr.Markdown("## 📄 Pregunta a tu PDF con IA")

    pdf = gr.File(label="Sube tu PDF")
    btn_pdf = gr.Button("Cargar PDF")
    estado = gr.Textbox(label="Estado", interactive=False)

    pregunta = gr.Textbox(label="Pregunta")
    btn_pregunta = gr.Button("Preguntar")
    respuesta = gr.Textbox(label="Respuesta", lines=8)

    btn_pdf.click(subir_pdf, inputs=pdf, outputs=estado)
    btn_pregunta.click(hacer_pregunta, inputs=pregunta, outputs=respuesta)

demo.launch()