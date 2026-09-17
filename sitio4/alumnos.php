<?php
/**
 * api/alumnos.php
 * GET  -> lista todos los alumnos, o filtra con ?q=texto (nombre/apellido/email/id)
 * POST -> agrega un nuevo alumno (recibe JSON)
 */

header('Content-Type: application/json; charset=utf-8');
require_once __DIR__ . '/../db.php';

$metodo = $_SERVER['REQUEST_METHOD'];

try {
    if ($metodo === 'GET') {
        $q = trim($_GET['q'] ?? '');

        if ($q !== '') {
            $sql = "SELECT * FROM Alumnos
                    WHERE nombre LIKE :q1
                       OR apellido LIKE :q2
                       OR email LIKE :q3
                       OR CAST(Alumno_id AS TEXT) = :id
                    ORDER BY Alumno_id DESC";
            $stmt = $pdo->prepare($sql);
            $like = '%' . $q . '%';
            $stmt->execute([
                ':q1' => $like,
                ':q2' => $like,
                ':q3' => $like,
                ':id' => $q,
            ]);
        } else {
            $stmt = $pdo->query("SELECT * FROM Alumnos ORDER BY Alumno_id DESC");
        }

        $alumnos = $stmt->fetchAll();
        echo json_encode(['success' => true, 'data' => $alumnos]);
        exit;
    }

    if ($metodo === 'POST') {
        $body = json_decode(file_get_contents('php://input'), true);

        if (!is_array($body)) {
            http_response_code(400);
            echo json_encode(['success' => false, 'error' => 'Datos inválidos enviados al servidor.']);
            exit;
        }

        $nombre           = trim($body['nombre'] ?? '');
        $apellido         = trim($body['apellido'] ?? '');
        $fecha_nacimiento = trim($body['fecha_nacimiento'] ?? '');
        $telefono         = trim($body['telefono'] ?? '');
        $email            = trim($body['email'] ?? '');

        // Validaciones
        $errores = [];
        if ($nombre === '')   $errores[] = 'El nombre es obligatorio.';
        if ($apellido === '') $errores[] = 'El apellido es obligatorio.';
        if ($email !== '' && !filter_var($email, FILTER_VALIDATE_EMAIL)) {
            $errores[] = 'El email no tiene un formato válido.';
        }
        if ($fecha_nacimiento !== '' && !preg_match('/^\d{4}-\d{2}-\d{2}$/', $fecha_nacimiento)) {
            $errores[] = 'La fecha de nacimiento debe tener formato AAAA-MM-DD.';
        }

        if (!empty($errores)) {
            http_response_code(422);
            echo json_encode(['success' => false, 'error' => implode(' ', $errores)]);
            exit;
        }

        $stmt = $pdo->prepare(
            "INSERT INTO Alumnos (nombre, apellido, fecha_nacimiento, telefono, email)
             VALUES (:nombre, :apellido, :fecha_nacimiento, :telefono, :email)"
        );
        $stmt->execute([
            ':nombre'           => $nombre,
            ':apellido'         => $apellido,
            ':fecha_nacimiento' => $fecha_nacimiento ?: null,
            ':telefono'         => $telefono ?: null,
            ':email'            => $email ?: null,
        ]);

        $nuevoId = $pdo->lastInsertId();
        $stmt = $pdo->prepare("SELECT * FROM Alumnos WHERE Alumno_id = :id");
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
