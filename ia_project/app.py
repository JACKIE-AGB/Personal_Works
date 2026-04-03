import streamlit as st
import requests

API_URL = "http://127.0.0.1:8001"

st.set_page_config(page_title="PDF Chatbot", layout="centered")

st.title("📄 Chatbot con PDF")
st.write("Haz preguntas sobre tu documento")

# Estado del chat
if "messages" not in st.session_state:
    st.session_state.messages = []

# Subir PDF
uploaded_file = st.file_uploader("Sube tu PDF", type="pdf")

if uploaded_file:
    with st.spinner("Procesando PDF..."):
        files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
        response = requests.post(f"{API_URL}/upload_pdf/", files=files)

    # ✅ Verifica si realmente funcionó
    if response.status_code == 200:
        st.success("PDF listo ✅")
    else:
        st.error(f"Error al procesar el PDF: {response.text}")

# Selector de estilo (opcional)
style = st.selectbox(
    "Estilo de respuesta",
    ["normal", "amable", "agresivo"]
)

# Mostrar chat
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# Input siempre activo
if prompt := st.chat_input("Escribe tu pregunta..."):
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Pensando..."):
            try:
                response = requests.post(
                    f"{API_URL}/ask/",
                    data={"question": prompt, "style": style}
                )

                if response.status_code == 200:
                    data = response.json()
                    answer = data.get("answer", "No se recibió respuesta.")
                else:
                    answer = f"Error {response.status_code}: {response.text}"

            except requests.exceptions.JSONDecodeError:
                answer = f"La API devolvió una respuesta inválida: {response.text}"
            except requests.exceptions.ConnectionError:
                answer = "No se pudo conectar con la API. ¿Está corriendo uvicorn?"
            except Exception as e:
                answer = f"Error inesperado: {str(e)}"

        st.write(answer)

    # ✅ Ahora dentro del if, después de definir answer
    st.session_state.messages.append({"role": "assistant", "content": answer})