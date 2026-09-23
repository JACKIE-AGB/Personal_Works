// server.js
// Backend Express + SQLite para la app escolar.
// Sirve el frontend (carpeta /public) y expone una API REST
// que el HTML/CSS/JS consume con fetch() para leer y escribir en la base de datos.

const path = require("path");
const fs = require("fs");
const express = require("express");
const Database = require("better-sqlite3");

const PORT = process.env.PORT || 3000;
const DB_PATH = path.join(__dirname, "db", "escuela.db");
const SCHEMA_PATH = path.join(__dirname, "db", "schema.sql");

// ---------- 1. Conectar / crear la base de datos ----------
const dbExisted = fs.existsSync(DB_PATH);
const db = new Database(DB_PATH);
db.pragma("foreign_keys = ON");

// Ejecuta el esquema siempre (usa IF NOT EXISTS, así que es seguro repetirlo)
const schema = fs.readFileSync(SCHEMA_PATH, "utf8");
db.exec(schema);

console.log(
  dbExisted
    ? `Base de datos existente cargada en ${DB_PATH}`
    : `Base de datos nueva creada en ${DB_PATH}`
);

// ---------- 2. Configurar servidor ----------
const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, "public")));

// ---------- 3. API: ALUMNOS ----------

// Listar alumnos, con búsqueda opcional por nombre/apellido/email (?q=texto)
app.get("/api/alumnos", (req, res) => {
  const q = (req.query.q || "").trim();
  let rows;
  if (q) {
    const like = `%${q}%`;
    rows = db
      .prepare(
        `SELECT * FROM alumnos
         WHERE nombre LIKE ? OR apellido LIKE ? OR email LIKE ?
         ORDER BY apellido, nombre`
      )
      .all(like, like, like);
  } else {
    rows = db.prepare(`SELECT * FROM alumnos ORDER BY apellido, nombre`).all();
  }
  res.json(rows);
});

// Obtener un alumno por id
app.get("/api/alumnos/:id", (req, res) => {
  const alumno = db
    .prepare(`SELECT * FROM alumnos WHERE alumno_id = ?`)
    .get(req.params.id);
  if (!alumno) return res.status(404).json({ error: "Alumno no encontrado" });
  res.json(alumno);
});

// Crear alumno
app.post("/api/alumnos", (req, res) => {
  const { nombre, apellido, fecha_nacimiento, telefono, email } = req.body;
  if (!nombre || !apellido) {
    return res.status(400).json({ error: "nombre y apellido son obligatorios" });
  }
  const stmt = db.prepare(
    `INSERT INTO alumnos (nombre, apellido, fecha_nacimiento, telefono, email)
     VALUES (?, ?, ?, ?, ?)`
  );
  const info = stmt.run(
    nombre,
    apellido,
    fecha_nacimiento || null,
    telefono || null,
    email || null
  );
  const nuevo = db
    .prepare(`SELECT * FROM alumnos WHERE alumno_id = ?`)
    .get(info.lastInsertRowid);
  res.status(201).json(nuevo);
});

// Actualizar alumno
app.put("/api/alumnos/:id", (req, res) => {
  const { nombre, apellido, fecha_nacimiento, telefono, email } = req.body;
  const existe = db
    .prepare(`SELECT * FROM alumnos WHERE alumno_id = ?`)
    .get(req.params.id);
  if (!existe) return res.status(404).json({ error: "Alumno no encontrado" });

  db.prepare(
    `UPDATE alumnos SET nombre = ?, apellido = ?, fecha_nacimiento = ?, telefono = ?, email = ?
     WHERE alumno_id = ?`
  ).run(
    nombre ?? existe.nombre,
    apellido ?? existe.apellido,
    fecha_nacimiento ?? existe.fecha_nacimiento,
    telefono ?? existe.telefono,
    email ?? existe.email,
    req.params.id
  );

  const actualizado = db
    .prepare(`SELECT * FROM alumnos WHERE alumno_id = ?`)
    .get(req.params.id);
  res.json(actualizado);
});

// Eliminar alumno (y en cascada sus colegiaturas/calificaciones)
app.delete("/api/alumnos/:id", (req, res) => {
  const info = db
    .prepare(`DELETE FROM alumnos WHERE alumno_id = ?`)
    .run(req.params.id);
  if (info.changes === 0)
    return res.status(404).json({ error: "Alumno no encontrado" });
  res.json({ ok: true });
});

// ---------- 4. API: COLEGIATURAS ----------

// Listar colegiaturas de un alumno
app.get("/api/alumnos/:id/colegiaturas", (req, res) => {
  const rows = db
    .prepare(
      `SELECT * FROM colegiaturas WHERE alumno_id = ? ORDER BY fecha_pago DESC`
    )
    .all(req.params.id);
  res.json(rows);
});

// Registrar un pago de colegiatura
app.post("/api/alumnos/:id/colegiaturas", (req, res) => {
  const { monto, fecha_pago, estado_pago } = req.body;
  if (monto === undefined || monto === null || monto === "") {
    return res.status(400).json({ error: "monto es obligatorio" });
  }
  const info = db
    .prepare(
      `INSERT INTO colegiaturas (alumno_id, monto, fecha_pago, estado_pago)
       VALUES (?, ?, ?, ?)`
    )
    .run(req.params.id, monto, fecha_pago || null, estado_pago || "pendiente");
  const nueva = db
    .prepare(`SELECT * FROM colegiaturas WHERE colegiatura_id = ?`)
    .get(info.lastInsertRowid);
  res.status(201).json(nueva);
});

// Eliminar una colegiatura
app.delete("/api/colegiaturas/:id", (req, res) => {
  const info = db
    .prepare(`DELETE FROM colegiaturas WHERE colegiatura_id = ?`)
    .run(req.params.id);
  if (info.changes === 0)
    return res.status(404).json({ error: "Registro no encontrado" });
  res.json({ ok: true });
});

// ---------- 5. API: CALIFICACIONES ----------

// Listar calificaciones de un alumno
app.get("/api/alumnos/:id/calificaciones", (req, res) => {
  const rows = db
    .prepare(
      `SELECT * FROM calificaciones WHERE alumno_id = ? ORDER BY periodo, materia`
    )
    .all(req.params.id);
  res.json(rows);
});

// Registrar una calificación
app.post("/api/alumnos/:id/calificaciones", (req, res) => {
  const { materia, nota, periodo } = req.body;
  if (!materia || nota === undefined || nota === null || nota === "") {
    return res.status(400).json({ error: "materia y nota son obligatorios" });
  }
  const info = db
    .prepare(
      `INSERT INTO calificaciones (alumno_id, materia, nota, periodo)
       VALUES (?, ?, ?, ?)`
    )
    .run(req.params.id, materia, nota, periodo || null);
  const nueva = db
    .prepare(`SELECT * FROM calificaciones WHERE calificacion_id = ?`)
    .get(info.lastInsertRowid);
  res.status(201).json(nueva);
});

// Eliminar una calificación
app.delete("/api/calificaciones/:id", (req, res) => {
  const info = db
    .prepare(`DELETE FROM calificaciones WHERE calificacion_id = ?`)
    .run(req.params.id);
  if (info.changes === 0)
    return res.status(404).json({ error: "Registro no encontrado" });
  res.json({ ok: true });
});

// ---------- 6. Arrancar servidor ----------
app.listen(PORT, () => {
  console.log(`\nServidor corriendo en http://localhost:${PORT}`);
  console.log("Presiona CTRL + C en esta ventana para apagarlo.\n");
});
