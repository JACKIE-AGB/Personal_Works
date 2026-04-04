import streamlit as st
import requests
import tkinter as tk
from tkinter import filedialog
import os

# Dirección de conexión con api_folders.py
API_URL = "http://127.0.0.1:8001" 

st.set_page_config(page_title="AI Folder Searcher", layout="centered", page_icon="📂")

def select_folder():
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    folder_selected = filedialog.askdirectory(master=root)
    root.destroy()
    return folder_selected

st.title("📂 Chatbot de Búsqueda (api_folders)")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "folder_path" not in st.session_state:
    st.session_state.folder_path = ""
if "indexed" not in st.session_state:
    st.session_state.indexed = False

# --- Zona de Selección de Carpeta ---
col_input, col_btn = st.columns([4, 1])
with col_input:
    path_input = st.text_input("Ruta de la carpeta a indexar", value=st.session_state.folder_path)
with col_btn:
    st.write(" ")
    if st.button("📁 Buscar"):
        selected = select_folder()
        if selected:
            st.session_state.folder_path = selected
            st.rerun()

col_index, col_clear = st.columns([1, 1])

with col_index:
    if st.button("🚀 Iniciar Indexación", use_container_width=True):
        current_path = st.session_state.folder_path if st.session_state.folder_path else path_input
        if current_path:
            with st.spinner("Conectando con api_folders y analizando..."):
                try:
                    response = requests.post(f"{API_URL}/index_folder/", data={"folder_path": current_path})
                    if response.status_code == 200:
                        data = response.json()
                        st.session_state.indexed = True
                        st.success(data["message"])
                        with st.expander("Archivos procesados correctamente"):
                            for f in data.get("files", []):
                                st.write(f"✅ {f}")
                    else:
                        st.error(f"Error en el servidor API: {response.text}")
                except Exception as e:
                    st.error(f"No se pudo conectar con api_folders.py. ¿Está encendido el servidor? Error: {e}")

with col_clear:
    if st.button("🗑️ Eliminar Índice", use_container_width=True):
        try:
            response = requests.post(f"{API_URL}/clear_index/")
            if response.status_code == 200:
                st.session_state.folder_path = ""
                st.session_state.indexed = False
                st.session_state.messages = []
                st.success("Índice eliminado. Puedes seleccionar una nueva carpeta.")
                st.rerun()
            else:
                st.error("Error al eliminar el índice.")
        except Exception as e:
            st.error(f"No se pudo conectar con api_folders.py. Error: {e}")

# --- Indicador de estado del índice ---
if st.session_state.indexed:
    st.info(f"📌 Carpeta activa: `{st.session_state.folder_path}` — El índice está cargado y listo. No necesitas volver a indexar.")
else:
    st.warning("⚠️ No hay ningún índice activo. Si ya indexaste antes, el servidor lo cargará automáticamente al reiniciarse.")

st.divider()

# --- Interfaz de Chat ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Pregunta sobre tus archivos indexados:"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Consultando a la base de datos de api_folders..."):
            try:
                response = requests.post(f"{API_URL}/ask/", data={"question": prompt, "style": "normal"})
                answer = response.json().get("answer", "No se recibió respuesta del servidor.")
                st.markdown(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})
            except:
                st.error("Error de comunicación con el backend.")