<?php
/**
 * api/alumno_detalle.php
 * GET ?id=X -> devuelve el alumno junto con sus colegiaturas y calificaciones
 */

header('Content-Type: application/json; charset=utf-8');
require_once __DIR__ . '/../db.php';

if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
    http_response_code(405);
    echo json_encode(['success' => false, 'error' => 'Método no permitido.']);
    exit;
}

$id = $_GET['id'] ?? null;
if (!$id || !ctype_digit((string)$id)) {
    http_response_code(400);
    echo json_encode(['success' => false, 'error' => 'Debes indicar un id de alumno válido.']);
    exit;
}

try {
    $stmt = $pdo->prepare("SELECT * FROM Alumnos WHERE Alumno_id = :id");
    $stmt->execute([':id' => $id]);
    $alumno = $stmt->fetch();

    if (!$alumno) {
        http_response_code(404);
        echo json_encode(['success' => false, 'error' => 'No se encontró ningún alumno con ese id.']);
        exit;
    }

    $stmtColeg = $pdo->prepare("SELECT * FROM Colegiaturas WHERE alumno_id = :id ORDER BY Colegiatura_id DESC");
    $stmtColeg->execute([':id' => $id]);

    $stmtCal = $pdo->prepare("SELECT * FROM Calificaciones WHERE alumno_id = :id ORDER BY calificacion_id DESC");
    $stmtCal->execute([':id' => $id]);

    echo json_encode([
        'success' => true,
        'data' => [
            'alumno'        => $alumno,
            'colegiaturas'  => $stmtColeg->fetchAll(),
            'calificaciones'=> $stmtCal->fetchAll(),
        ]
    ]);

} catch (PDOException $e) {
    http_response_code(500);
    echo json_encode(['success' => false, 'error' => 'Error en la base de datos: ' . $e->getMessage()]);
}
