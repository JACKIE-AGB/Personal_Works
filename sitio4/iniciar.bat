@echo off
cd /d "%~dp0"

IF NOT EXIST node_modules (
  echo Instalando dependencias, solo la primera vez...
  call npm install
)

echo Iniciando servidor...
call npm start
pause
