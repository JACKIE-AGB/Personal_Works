# Gestión Escolar — App local (Alumnos, Colegiaturas, Calificaciones)

App completa **de cero a funcionando**: un frontend en HTML/CSS/JS conectado
directamente, a través de un backend en Node.js (Express), a una base de
datos real en SQLite. Todo corre en tu computadora, en un servidor local que
puedes encender y apagar cuando quieras.

## ¿Cómo está conectado todo?

```
Navegador (index.html + app.js)
        │  fetch()  →  peticiones HTTP (GET/POST/PUT/DELETE)
        ▼
server.js (Express)  →  expone la API en /api/...
        │
        ▼
db/escuela.db  (base de datos SQLite, con las 3 tablas)
```

- `app.js` nunca inventa ni "quema" datos: todo alumno que ves en la página
  viene de una consulta real a la base de datos (`GET /api/alumnos`).
- Al llenar el formulario y darle "Agregar alumno", el navegador manda un
  `POST /api/alumnos`, el servidor lo guarda en SQLite, y la tabla en pantalla
  se refresca leyendo de nuevo la base de datos.
- Lo mismo aplica para colegiaturas y calificaciones (dentro del botón "Ver"
  de cada alumno).

## Tablas de la base de datos

- **alumnos**: `alumno_id, nombre, apellido, fecha_nacimiento, telefono, email`
- **colegiaturas**: `colegiatura_id, alumno_id, monto, fecha_pago, estado_pago`
- **calificaciones**: `calificacion_id, alumno_id, materia, nota, periodo`

El archivo `db/escuela.db` se crea automáticamente la primera vez que
enciendes el servidor (no tienes que instalar MySQL, Postgres, ni nada
aparte — SQLite es un solo archivo).

## Requisito único: Node.js

Necesitas tener instalado **Node.js** (versión 18 o superior).
Descárgalo gratis aquí si no lo tienes: https://nodejs.org

Para checar si ya lo tienes, abre una terminal y escribe:
```
node -v
```

## Cómo encender el servidor

### Windows
Haz doble clic en **`iniciar.bat`**.
(La primera vez tardará un poco más porque instala las dependencias.)

### Mac / Linux
Abre una terminal en esta carpeta y ejecuta:
```
./iniciar.sh
```

### Manualmente (cualquier sistema)
```
npm install      # solo la primera vez
npm start
```

Cuando veas en la terminal:
```
Servidor corriendo en http://localhost:3000
```
abre tu navegador en **http://localhost:3000** y ahí está la app.

## Cómo apagar el servidor

Con la ventana de la terminal donde corre el servidor activa, presiona:
```
CTRL + C
```

Para volver a prenderlo, repite el paso "Cómo encender el servidor" —
tus datos **no se pierden**, siguen guardados en `db/escuela.db`.

## Qué puedes hacer en la app

- **Agregar alumno**: llena el formulario de arriba y da clic en "Agregar alumno".
- **Buscar alumnos**: escribe en la barra de búsqueda (busca por nombre,
  apellido o email) y da clic en "Buscar", o presiona Enter.
- **Editar / Eliminar**: cada fila de la tabla tiene sus botones.
- **Ver detalle**: el botón "Ver" abre un panel donde puedes registrar y ver
  las colegiaturas y calificaciones de ese alumno.

## Estructura del proyecto

```
escuela-app/
├── server.js          Backend Express (la API que conecta con SQLite)
├── package.json        Dependencias del proyecto
├── db/
│   ├── schema.sql      Definición de las 3 tablas
│   └── escuela.db       Se crea solo al encender el servidor (aquí viven tus datos)
├── public/
│   ├── index.html      Estructura de la página
│   ├── style.css        Estilos
│   └── app.js            Lógica que conecta el HTML con la API (fetch)
├── iniciar.sh           Encender en Mac/Linux
└── iniciar.bat          Encender en Windows
```

## Si algo falla

- **"npm no se reconoce como comando"** → no tienes Node.js instalado,
  bájalo de https://nodejs.org y reinicia la terminal.
- **"Puerto 3000 en uso"** → cierra cualquier otro servidor que esté usando
  ese puerto, o edita `server.js` y cambia `const PORT = process.env.PORT || 3000;`
  por otro número, por ejemplo `4000`.
- **Quiero borrar todos los datos y empezar de cero** → apaga el servidor y
  borra el archivo `db/escuela.db`; se creará una base de datos nueva y vacía
  la próxima vez que enciendas el servidor.
