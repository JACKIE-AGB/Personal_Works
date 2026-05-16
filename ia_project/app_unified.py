import streamlit as st
import requests
import tkinter as tk
from tkinter import filedialog

API_URL = "http://127.0.0.1:8001"

st.set_page_config(
    page_title="CFE Intelligent Assistant",
    page_icon="⚡",
    layout="wide"
)

# ==========================================================
# STATES
# ==========================================================
if "pdf_messages" not in st.session_state:
    st.session_state.pdf_messages = []

if "folder_messages" not in st.session_state:
    st.session_state.folder_messages = []

if "folder_path" not in st.session_state:
    st.session_state.folder_path = ""

if "indexed" not in st.session_state:
    st.session_state.indexed = False

if "pdf_loaded" not in st.session_state:
    st.session_state.pdf_loaded = False

# ==========================================================
# SELECT FOLDER
# ==========================================================
def select_folder():
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    folder_selected = filedialog.askdirectory(master=root)
    root.destroy()
    return folder_selected

# ==========================================================
# TITLE
# ==========================================================
st.title("⚡ Asistente Inteligente CFE")

tab1, tab2 = st.tabs([
    "📄 Documento Individual",
    "📂 Biblioteca Documental"
])

# ==========================================================
# TAB PDF
# ==========================================================
with tab1:
    st.subheader("📄 Análisis Individual")

    uploaded_file = st.file_uploader(
        "Sube un PDF o Plano",
        type="pdf"
    )

    col1, col2 = st.columns(2)

    with col1:
        if uploaded_file and not st.session_state.pdf_loaded:
            if st.button("📤 Procesar PDF"):
                with st.spinner("Procesando documento e imágenes incorporadas..."):
                    files = {
                        "file": (
                            uploaded_file.name,
                            uploaded_file.getvalue(),
                            "application/pdf"
                        )
                    }
                    res = requests.post(f"{API_URL}/upload_pdf/", files=files)

                    if res.status_code == 200:
                        st.session_state.pdf_loaded = True
                        st.success("✅ PDF y elementos visuales procesados con éxito.")
                    else:
                        st.error(res.json().get("error", "Error desconocido"))
                        
        elif st.session_state.pdf_loaded:
            st.success("✅ PDF cargado y activo en el sistema.")

    with col2:
        if st.button("🗑️ Limpiar PDF"):
            st.session_state.pdf_messages = []
            st.session_state.pdf_loaded = False
            requests.post(f"{API_URL}/clear_index/")
            st.rerun()

    st.divider()

    for msg in st.session_state.pdf_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Pregunta sobre el documento o plano cargado..."):
        st.session_state.pdf_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)

        with st.spinner("Analizando información textual y visual..."):
            res = requests.post(
                f"{API_URL}/ask_pdf/",
                data={"question": prompt}
            )
            ans = res.json().get("answer", "Error al obtener respuesta.")

        with st.chat_message("assistant"):
            st.markdown(ans)

        st.session_state.pdf_messages.append({"role": "assistant", "content": ans})

# ==========================================================
# TAB FOLDER
# ==========================================================
with tab2:
    st.subheader("📂 Biblioteca Documental")

    col_input, col_btn = st.columns([4, 1])

    with col_input:
        path_input = st.text_input(
            "Ruta de carpeta en el servidor:",
            value=st.session_state.folder_path
        )
        if path_input != st.session_state.folder_path:
            st.session_state.folder_path = path_input

    with col_btn:
        st.write("")
        if st.button("📁 Buscar"):
            selected = select_folder()
            if selected:
                st.session_state.folder_path = selected
                st.rerun()

    col3, col4 = st.columns(2)

    with col3:
        if st.button("🚀 Indexar"):
            if st.session_state.folder_path:
                with st.spinner("Indexando documentos y leyendo planos con IA de Visión (esto puede tomar unos minutos)..."):
                    res = requests.post(
                        f"{API_URL}/index_folder/",
                        data={"folder_path": st.session_state.folder_path}
                    )

                    if res.status_code == 200:
                        st.session_state.indexed = True
                        st.success(res.json().get("message"))
                    else:
                        st.error(res.json().get("error", "Error interno al indexar."))
            else:
                st.warning("Selecciona carpeta")

    with col4:
        if st.button("🗑️ Eliminar Índice"):
            requests.post(f"{API_URL}/clear_index/")
            st.session_state.indexed = False
            st.session_state.folder_messages = []
            st.rerun()

    if st.session_state.indexed:
        st.info(f"📌 Carpeta activa en el sistema: {st.session_state.folder_path}")

    st.divider()

    for msg in st.session_state.folder_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt_f := st.chat_input("Pregunta sobre la biblioteca técnica..."):
        st.session_state.folder_messages.append({"role": "user", "content": prompt_f})
        with st.chat_message("user"):
            st.write(prompt_f)

        with st.spinner("Consultando bases de datos y análisis visual..."):
            res = requests.post(
                f"{API_URL}/ask_folder/",
                data={"question": prompt_f}
            )
            data = res.json()
            ans = data.get("answer", "No se obtuvo respuesta del modelo.")
            sources = data.get("sources", [])

            if sources:
                ans += "\n\n### 📁 Archivos fuente asociados:\n"
                for s in sources:
                    ans += f"- `{s}`\n"

        with st.chat_message("assistant"):
            st.markdown(ans)

        st.session_state.folder_messages.append({"role": "assistant", "content": ans})