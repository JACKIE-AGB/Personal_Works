<?php
/**
 * api/calificaciones.php
 * GET  ?alumno_id=X -> lista calificaciones (de un alumno, o todas si no se manda)
 * POST -> agrega una nueva calificación (recibe JSON)
 */

header('Content-Type: application/json; charset=utf-8');
require_once __DIR__ . '/../db.php';

$metodo = $_SERVER['REQUEST_METHOD'];

try {
    if ($metodo === 'GET') {
        $alumnoId = $_GET['alumno_id'] ?? null;

        if ($alumnoId) {
            $stmt = $pdo->prepare("SELECT * FROM Calificaciones WHERE alumno_id = :id ORDER BY calificacion_id DESC");
            $stmt->execute([':id' => $alumnoId]);
        } else {
            $stmt = $pdo->query("SELECT * FROM Calificaciones ORDER BY calificacion_id DESC");
        }

        echo json_encode(['success' => true, 'data' => $stmt->fetchAll()]);
        exit;
    }

    if ($metodo === 'POST') {
        $body = json_decode(file_get_contents('php://input'), true);
        if (!is_array($body)) {
            http_response_code(400);
            echo json_encode(['success' => false, 'error' => 'Datos inválidos enviados al servidor.']);
            exit;
        }

        $alumno_id = $body['alumno_id'] ?? null;
        $materia   = trim($body['materia'] ?? '');
        $nota      = $body['nota'] ?? null;
        $periodo   = trim($body['periodo'] ?? '');

        $errores = [];
        if (!$alumno_id || !ctype_digit((string)$alumno_id)) $errores[] = 'Falta el alumno.';
        if ($materia === '') $errores[] = 'La materia es obligatoria.';
        if ($nota === null || !is_numeric($nota) || $nota < 0 || $nota > 10) {
            $errores[] = 'La nota debe ser un número entre 0 y 10.';
        }
        if ($periodo === '') $errores[] = 'El periodo es obligatorio.';

        if (empty($errores)) {
            $chk = $pdo->prepare("SELECT 1 FROM Alumnos WHERE Alumno_id = :id");
            $chk->execute([':id' => $alumno_id]);
            if (!$chk->fetch()) {
                $errores[] = 'El alumno indicado no existe.';
            }
        }

        if (!empty($errores)) {
            http_response_code(422);
            echo json_encode(['success' => false, 'error' => implode(' ', $errores)]);
            exit;
        }

        $stmt = $pdo->prepare(
            "INSERT INTO Calificaciones (alumno_id, materia, nota, periodo)
             VALUES (:alumno_id, :materia, :nota, :periodo)"
        );
        $stmt->execute([
            ':alumno_id' => $alumno_id,
            ':materia'   => $materia,
            ':nota'      => $nota,
            ':periodo'   => $periodo,
        ]);

        $nuevoId = $pdo->lastInsertId();
        $stmt = $pdo->prepare("SELECT * FROM Calificaciones WHERE calificacion_id = :id");
        $stmt->execute([':id' => $nuevoId]);

        echo json_encode(['success' => true, 'data' => $stmt->fetch()]);
        exit;
    }

    http_response_code(405);
    echo json_encode(['success' => false, 'error' => 'Método no permitido.']);

} catch (PDOException $e) {
    http_response_code(500);
    echo json_encode(['success' => false, 'error' => 'Error en la base de datos: ' . $e->getMessage()]);
}
