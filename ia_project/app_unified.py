import streamlit as st
import requests
import os
import tkinter as tk
from tkinter import filedialog

API_URL = "http://127.0.0.1:8001"

st.set_page_config(page_title="Asistente IA Unificado", layout="centered", page_icon="🤖")

# Inicialización de estados
if "pdf_messages" not in st.session_state: st.session_state.pdf_messages = []
if "folder_messages" not in st.session_state: st.session_state.folder_messages = []
if "folder_path" not in st.session_state: st.session_state.folder_path = ""
if "indexed" not in st.session_state: st.session_state.indexed = False

def select_folder():
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    folder_selected = filedialog.askdirectory(master=root)
    root.destroy()
    return folder_selected

st.title("🤖 Asistente Inteligente Unificado")

tab1, tab2 = st.tabs(["📄 Chat PDF Individual", "📂 Chat con Carpetas"])

# ============================================
# TAB 1: PDF INDIVIDUAL
# ============================================
with tab1:
    st.markdown("### 📄 Preguntas sobre un PDF")
    uploaded_file = st.file_uploader("Sube tu archivo", type="pdf")

    col1, col2 = st.columns([3, 1])
    with col1:
        if uploaded_file and st.button("📤 Procesar"):
            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
            res = requests.post(f"{API_URL}/upload_pdf/", files=files)
            if res.status_code == 200:
                st.success("✅ PDF Listo")
            else:
                st.error(f"❌ Error: {res.json().get('error', 'Desconocido')}")
    with col2:
        if st.button("🗑️ Limpiar", key="c1"):
            st.session_state.pdf_messages = []
            st.rerun()

    style = st.selectbox("Estilo", ["normal", "amable", "agresivo"])

    for msg in st.session_state.pdf_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Pregunta algo...", key="in1"):
        st.session_state.pdf_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)
        res = requests.post(f"{API_URL}/ask_pdf/", data={"question": prompt, "style": style})
        ans = res.json().get("answer", "Error")
        with st.chat_message("assistant"):
            st.write(ans)
        st.session_state.pdf_messages.append({"role": "assistant", "content": ans})

# ============================================
# TAB 2: CARPETA
# ============================================
with tab2:
    st.markdown("### 📂 Búsqueda en Biblioteca de Documentos")

    col_input, col_btn = st.columns([4, 1])
    with col_input:
        path_input = st.text_input("Ruta de la carpeta", value=st.session_state.folder_path)
        # ✅ FIX #3: sincronizar el texto escrito manualmente al estado de sesión
        if path_input != st.session_state.folder_path:
            st.session_state.folder_path = path_input

    with col_btn:
        st.write(" ")
        if st.button("📁 Buscar"):
            selected = select_folder()
            if selected:
                st.session_state.folder_path = selected
                st.rerun()

    col_idx, col_clr = st.columns(2)
    with col_idx:
        if st.button("🚀 Iniciar Indexación", use_container_width=True):
            if st.session_state.folder_path:
                with st.spinner("Indexando..."):
                    res = requests.post(f"{API_URL}/index_folder/", data={"folder_path": st.session_state.folder_path})
                    if res.status_code == 200:
                        st.session_state.indexed = True
                        data = res.json()
                        st.success(f"✅ {data.get('message', 'Indexación completa')}")
                    else:
                        st.error(f"❌ Error: {res.json().get('error', 'Desconocido')}")
            else:
                st.warning("⚠️ Selecciona una carpeta primero.")

    with col_clr:
        if st.button("🗑️ Eliminar Índice", use_container_width=True):
            requests.post(f"{API_URL}/clear_index/")
            st.session_state.indexed = False
            st.session_state.folder_path = ""
            st.session_state.folder_messages = []
            st.rerun()

    if st.session_state.indexed:
        st.info(f"📌 Carpeta activa: `{st.session_state.folder_path}`")

    st.divider()

    for msg in st.session_state.folder_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt_f := st.chat_input("Pregunta sobre la carpeta...", key="in2"):
        st.session_state.folder_messages.append({"role": "user", "content": prompt_f})
        with st.chat_message("user"):
            st.write(prompt_f)
        res = requests.post(f"{API_URL}/ask_folder/", data={"question": prompt_f})
        ans = res.json().get("answer", "Error de conexión")
        with st.chat_message("assistant"):
            st.markdown(ans)
        st.session_state.folder_messages.append({"role": "assistant", "content": ans})