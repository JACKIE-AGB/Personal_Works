import streamlit as st
import requests
import tkinter as tk
from tkinter import filedialog

API_URL = "http://127.0.0.1:8001"

st.set_page_config(
    page_title="CFE Intelligent Assistant & Vision",
    page_icon="⚡",
    layout="wide"
)

# ==========================================================
# ESTADOS DE SESIÓN
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
# SELECCIÓN DE CARPETA (TKINTER)
# ==========================================================
def select_folder():
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    folder_selected = filedialog.askdirectory(master=root)
    root.destroy()
    return folder_selected


# ==========================================================
# INTERFAZ DE USUARIO
# ==========================================================
st.title("⚡ Asistente Inteligente CFE (Texto e Ingeniería de Planos)")

tab1, tab2 = st.tabs([
    "📄 Documento Individual (Con Visión)",
    "📂 Biblioteca Documental Completa"
])

# ==========================================================
# PESTAÑA 1: ANALISIS DE PDF INDIVIDUAL
# ==========================================================
with tab1:
    st.subheader("📄 Análisis Individual de Documentos y Planos")

    uploaded_file = st.file_uploader(
        "Sube un archivo PDF o Plano Técnico",
        type="pdf"
    )

    col1, col2 = st.columns(2)

    with col1:
        if uploaded_file and not st.session_state.pdf_loaded:
            if st.button("📤 Procesar PDF y Gráficos"):
                with st.spinner("Analizando texto e interpretando imágenes/planos con IA..."):
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
                        st.success("✅ Documento y planos procesados con éxito.")
                    else:
                        st.error(res.json().get("error", "Error desconocido."))
                        
        elif st.session_state.pdf_loaded:
            st.success("✅ Documento actualmente activo y cargado.")

    with col2:
        if st.button("🗑️ Limpiar Memoria PDF"):
            st.session_state.pdf_messages = []
            st.session_state.pdf_loaded = False
            requests.post(f"{API_URL}/clear_index/")
            st.rerun()

    st.divider()

    # Historial de chat
    for msg in st.session_state.pdf_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Pregunta sobre el texto o diagramas del documento..."):
        st.session_state.pdf_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)

        with st.spinner("Buscando en texto y análisis de visión..."):
            res = requests.post(
                f"{API_URL}/ask_pdf/",
                data={"question": prompt, "style": "normal"}
            )
            ans = res.json().get("answer", "Error al conectar con el servidor.")

        with st.chat_message("assistant"):
            st.markdown(ans)

        st.session_state.pdf_messages.append({"role": "assistant", "content": ans})


# ==========================================================
# PESTAÑA 2: BIBLIOTECA DOCUMENTAL (CARPETAS)
# ==========================================================
with tab2:
    st.subheader("📂 Biblioteca Documental e Historial de Planos")

    col_input, col_btn = st.columns([4, 1])

    with col_input:
        path_input = st.text_input(
            "Ruta de la carpeta local en el servidor:",
            value=st.session_state.folder_path
        )
        if path_input != st.session_state.folder_path:
            st.session_state.folder_path = path_input

    with col_btn:
        st.write("")
        if st.button("📁 Explorar"):
            selected = select_folder()
            if selected:
                st.session_state.folder_path = selected
                st.rerun()

    col3, col4 = st.columns(2)

    with col3:
        if st.button("🚀 Iniciar Indexación Avanzada"):
            if st.session_state.folder_path:
                with st.spinner("Indexando biblioteca. Procesando texto y convirtiendo planos con IA de Visión (puede demorar)..."):
                    res = requests.post(
                        f"{API_URL}/index_folder/",
                        data={"folder_path": st.session_state.folder_path}
                    )

                    if res.status_code == 200:
                        st.session_state.indexed = True
                        st.success(res.json().get("message"))
                    else:
                        st.error(res.json().get("error"))
            else:
                st.warning("Por favor, selecciona una ruta de carpeta válida primero.")

    with col4:
        if st.button("🗑️ Eliminar Índice de Biblioteca"):
            requests.post(f"{API_URL}/clear_index/")
            st.session_state.indexed = False
            st.session_state.folder_messages = []
            st.rerun()

    if st.session_state.indexed:
        st.info(f"📌 Carpeta activa en el sistema: `{st.session_state.folder_path}`")

    st.divider()

    # Historial de chat de la biblioteca
    for msg in st.session_state.folder_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt_f := st.chat_input("Pregunta general sobre la biblioteca técnica o planos..."):
        st.session_state.folder_messages.append({"role": "user", "content": prompt_f})
        with st.chat_message("user"):
            st.write(prompt_f)

        with st.spinner("Consultando base de conocimiento técnica..."):
            res = requests.post(
                f"{API_URL}/ask_folder/",
                data={"question": prompt_f}
            )
            data = res.json()
            ans = data.get("answer", "Error al procesar la respuesta.")

        with st.chat_message("assistant"):
            st.markdown(ans)

        st.session_state.folder_messages.append({"role": "assistant", "content": ans})