#!/bin/bash
# Prende el servidor local. Si es la primera vez, instala dependencias.
cd "$(dirname "$0")"

if [ ! -d "node_modules" ]; then
  echo "Instalando dependencias (solo la primera vez)..."
  npm install
fi

echo "Iniciando servidor..."
npm start
