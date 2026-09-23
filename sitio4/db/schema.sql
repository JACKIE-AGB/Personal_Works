-- Esquema de la base de datos escuela.db

CREATE TABLE IF NOT EXISTS alumnos (
    alumno_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre            TEXT NOT NULL,
    apellido          TEXT NOT NULL,
    fecha_nacimiento  TEXT,
    telefono          TEXT,
    email             TEXT
);

CREATE TABLE IF NOT EXISTS colegiaturas (
    colegiatura_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    alumno_id       INTEGER NOT NULL,
    monto           REAL NOT NULL,
    fecha_pago      TEXT,
    estado_pago     TEXT,
    FOREIGN KEY (alumno_id) REFERENCES alumnos(alumno_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS calificaciones (
    calificacion_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    alumno_id        INTEGER NOT NULL,
    materia          TEXT NOT NULL,
    nota             REAL NOT NULL,
    periodo          TEXT,
    FOREIGN KEY (alumno_id) REFERENCES alumnos(alumno_id) ON DELETE CASCADE
);
