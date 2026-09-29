# El Multiverso (Node.js + Express)

## Cómo ejecutarlo
1. Instala Node.js (v18 o superior): https://nodejs.org
2. En esta carpeta:  `npm install`  y luego  `npm start`
3. Abre http://localhost:3000

## Cuentas creadas desde el inicio
| ID   | Contraseña | Tipo          |
|------|-----------|---------------|
| 0000 | Progweb2# | Administrador (PT) |
| 9999 | Progweb2# | Cliente (CT)       |

## Imágenes
Copia tus imágenes a `public/img/` con los nombres indicados en `public/img/LEEME.txt`
(5 del carrusel, 3 de categorías y 1 de fondo para las páginas de pedidos).
Mientras no estén, la página muestra un aviso con el nombre del archivo que falta.

## Estructura
- `server.js` – servidor, API y protección de páginas por tipo de usuario
- `data/` – se crea solo; guarda usuarios.json y pedidos.json
- `public/` – páginas HTML, css/estilos.css y js/app.js (barra superior compartida)
