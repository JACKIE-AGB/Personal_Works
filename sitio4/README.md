# Sistema de Registro y Consulta de Alumnos

Aplicación local con **frontend en HTML/CSS/JS** y **backend en PHP**,
comunicados por una API PHP que devuelve JSON. La base de datos usa
**SQLite** (a través de PDO) para que todo funcione con un solo comando,
sin necesidad de instalar/configurar MySQL aparte.

## 📁 Estructura

```
proyecto-alumnos/
├── index.html                 <- Frontend (se abre en el navegador)
├── css/style.css
├── js/app.js                  <- Consume la API con fetch()
├── db.php                     <- Conexión PDO + creación de tablas + datos de ejemplo
├── api/
│   ├── alumnos.php            <- GET (listar/buscar) y POST (crear) alumnos
│   ├── alumno_detalle.php     <- GET detalle de un alumno + sus colegiaturas y calificaciones
│   ├── colegiaturas.php       <- GET y POST de colegiaturas
│   └── calificaciones.php     <- GET y POST de calificaciones
└── data/
    └── alumnos.db             <- Se crea automáticamente la primera vez (SQLite)
```

## ▶️ Cómo levantar el proyecto

Requisitos: tener **PHP instalado** (con la extensión `pdo_sqlite`, que
viene habilitada por defecto en la mayoría de instalaciones de PHP).

1. Abre una terminal dentro de la carpeta `proyecto-alumnos`.
2. Ejecuta:
   ```bash
   php -S localhost:8000
   ```
3. Abre tu navegador en:
   ```
   http://localhost:8000/index.html
   ```

Al abrir la página verás automáticamente los alumnos que ya existen en
la base de datos (la primera vez se crean 3 alumnos de ejemplo, con
algunas colegiaturas y calificaciones, para que no empieces con la
tabla vacía).

## 🗃️ Tablas (idénticas en frontend y backend)

- **Alumnos**: `Alumno_id, nombre, apellido, fecha_nacimiento, telefono, email`
- **Colegiaturas**: `Colegiatura_id, alumno_id, monto, mes_pago, fecha_pago, estado_pago`
- **Calificaciones**: `calificacion_id, alumno_id, materia, nota, periodo`

## ✅ Funcionalidad implementada

- **Agregar Alumno**: formulario con validación (nombre/apellido obligatorios,
  email con formato válido, fecha en formato AAAA-MM-DD). Se guarda directo
  en la base de datos vía `POST` a `api/alumnos.php`.
- **Buscar Alumno**: búsqueda por nombre, apellido, email o ID (`GET` a
  `api/alumnos.php?q=...`).
- **Ver detalle de un alumno**: muestra sus colegiaturas y calificaciones,
  con formularios para agregar nuevos registros de cada una.
- **Warnings/errores**: cualquier error de validación, de conexión con el
  servidor, o de base de datos se muestra como una alerta visual en la
  esquina superior derecha (rojo = error, amarillo = advertencia,
  verde = éxito).

## 🔁 Reiniciar los datos

Si quieres borrar todo y volver a los datos de ejemplo, simplemente borra
el archivo `data/alumnos.db` y vuelve a levantar el servidor; se creará
de nuevo automáticamente.

## 🐬 ¿Prefieres usar MySQL en vez de SQLite?

Abre `db.php`: al final del archivo hay un bloque comentado con la
conexión equivalente por PDO+MySQL. Solo tendrías que:
1. Comentar el bloque de conexión SQLite (arriba del archivo).
2. Descomentar el bloque de MySQL y ajustar usuario/contraseña.
3. Crear la base de datos `alumnos_db` en tu MySQL local.
4. Cambiar `AUTOINCREMENT` por `AUTO_INCREMENT` en los `CREATE TABLE`.

El resto del proyecto (API y frontend) no necesita ningún cambio, porque
solo interactúan con la variable `$pdo`.
