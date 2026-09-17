<?php
/**
 * db.php
 * Conexión a la base de datos (SQLite vía PDO) + creación de tablas
 * + datos de ejemplo (solo la primera vez que se ejecuta).
 *
 * SQLite se usa para que el proyecto funcione 100% en local con un solo
 * comando (php -S localhost:8000), sin tener que instalar/configurar
 * un servidor MySQL aparte. El archivo de la base de datos se crea
 * automáticamente en /data/alumnos.db
 *
 * Si prefieres usar MySQL, al final de este archivo hay un bloque
 * comentado con la conexión equivalente por PDO+MySQL.
 */

$dbFile = __DIR__ . '/data/alumnos.db';
$esNueva = !file_exists($dbFile);

try {
    $pdo = new PDO('sqlite:' . $dbFile);
    $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    $pdo->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE, PDO::FETCH_ASSOC);
    $pdo->exec('PRAGMA foreign_keys = ON;');
} catch (PDOException $e) {
    http_response_code(500);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode([
        'success' => false,
        'error'   => 'No se pudo conectar a la base de datos: ' . $e->getMessage()
    ]);
    exit;
}

function crearTablas(PDO $pdo): void
{
    $pdo->exec("
        CREATE TABLE IF NOT EXISTS Alumnos (
            Alumno_id         INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre            TEXT NOT NULL,
            apellido          TEXT NOT NULL,
            fecha_nacimiento  TEXT,
            telefono          TEXT,
            email             TEXT
        )
    ");

    $pdo->exec("
        CREATE TABLE IF NOT EXISTS Colegiaturas (
            Colegiatura_id INTEGER PRIMARY KEY AUTOINCREMENT,
            alumno_id      INTEGER NOT NULL,
            monto          REAL NOT NULL,
            mes_pago       TEXT NOT NULL,
            fecha_pago     TEXT,
            estado_pago    TEXT NOT NULL DEFAULT 'Pendiente',
            FOREIGN KEY (alumno_id) REFERENCES Alumnos(Alumno_id) ON DELETE CASCADE
        )
    ");

    $pdo->exec("
        CREATE TABLE IF NOT EXISTS Calificaciones (
            calificacion_id INTEGER PRIMARY KEY AUTOINCREMENT,
            alumno_id       INTEGER NOT NULL,
            materia         TEXT NOT NULL,
            nota            REAL NOT NULL,
            periodo         TEXT NOT NULL,
            FOREIGN KEY (alumno_id) REFERENCES Alumnos(Alumno_id) ON DELETE CASCADE
        )
    ");
}

function sembrarDatos(PDO $pdo): void
{
    $alumnos = [
        ['Ana',    'García',   '2005-03-12', '3111234567', 'ana.garcia@example.com'],
        ['Luis',   'Martínez', '2004-11-02', '3117654321', 'luis.martinez@example.com'],
        ['Sofía',  'Hernández','2006-07-25', '3119876543', 'sofia.hernandez@example.com'],
    ];

    $stmtAlumno = $pdo->prepare(
        "INSERT INTO Alumnos (nombre, apellido, fecha_nacimiento, telefono, email)
         VALUES (:nombre, :apellido, :fecha_nacimiento, :telefono, :email)"
    );

    $idsAlumnos = [];
    foreach ($alumnos as $a) {
        $stmtAlumno->execute([
            ':nombre'           => $a[0],
            ':apellido'         => $a[1],
            ':fecha_nacimiento' => $a[2],
            ':telefono'         => $a[3],
            ':email'            => $a[4],
        ]);
        $idsAlumnos[] = $pdo->lastInsertId();
    }

    $stmtColeg = $pdo->prepare(
        "INSERT INTO Colegiaturas (alumno_id, monto, mes_pago, fecha_pago, estado_pago)
         VALUES (:alumno_id, :monto, :mes_pago, :fecha_pago, :estado_pago)"
    );
    $colegiaturas = [
        [$idsAlumnos[0], 1500.00, 'Enero',  '2025-01-05', 'Pagado'],
        [$idsAlumnos[0], 1500.00, 'Febrero', null,        'Pendiente'],
        [$idsAlumnos[1], 1500.00, 'Enero',  '2025-01-10', 'Pagado'],
        [$idsAlumnos[2], 1500.00, 'Enero',  null,         'Pendiente'],
    ];
    foreach ($colegiaturas as $c) {
        $stmtColeg->execute([
            ':alumno_id'   => $c[0],
            ':monto'       => $c[1],
            ':mes_pago'    => $c[2],
            ':fecha_pago'  => $c[3],
            ':estado_pago' => $c[4],
        ]);
    }

    $stmtCal = $pdo->prepare(
        "INSERT INTO Calificaciones (alumno_id, materia, nota, periodo)
         VALUES (:alumno_id, :materia, :nota, :periodo)"
    );
    $calificaciones = [
        [$idsAlumnos[0], 'Matemáticas', 9.2, '2025-1'],
        [$idsAlumnos[0], 'Español',     8.7, '2025-1'],
        [$idsAlumnos[1], 'Matemáticas', 7.5, '2025-1'],
        [$idsAlumnos[2], 'Historia',    9.8, '2025-1'],
    ];
    foreach ($calificaciones as $c) {
        $stmtCal->execute([
            ':alumno_id' => $c[0],
            ':materia'   => $c[1],
            ':nota'      => $c[2],
            ':periodo'   => $c[3],
        ]);
    }
}

crearTablas($pdo);
if ($esNueva) {
    sembrarDatos($pdo);
}

/*
=====================================================================
 ALTERNATIVA: Conexión por MySQL en lugar de SQLite
 (Descomenta esto y borra/comenta el bloque de arriba si prefieres
 usar un servidor MySQL local, por ejemplo con XAMPP/WAMP/MAMP)
=====================================================================

$host   = '127.0.0.1';
$dbname = 'alumnos_db';
$user   = 'root';
$pass   = '';

try {
    $pdo = new PDO("mysql:host=$host;dbname=$dbname;charset=utf8mb4", $user, $pass);
    $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    $pdo->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE, PDO::FETCH_ASSOC);
} catch (PDOException $e) {
    http_response_code(500);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode(['success' => false, 'error' => 'Error de conexión: ' . $e->getMessage()]);
    exit;
}
// Recuerda crear la base de datos "alumnos_db" y correr el mismo
// CREATE TABLE de arriba (cambiando AUTOINCREMENT por AUTO_INCREMENT).
*/
