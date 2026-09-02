<?php

require_once "conexion.php";


// ================================
// CONSULTAR ALUMNOS
// ================================

$sql_alumnos = "SELECT * FROM alumnos";
$resultado_alumnos = $conexion->query($sql_alumnos);


// ================================
// CONSULTAR COLEGIATURAS
// ================================

$sql_colegiaturas = "SELECT * FROM colegiatura";
$resultado_colegiaturas = $conexion->query($sql_colegiaturas);


// ================================
// CONSULTAR CALIFICACIONES
// ================================

$sql_calificaciones = "SELECT * FROM calificaciones";
$resultado_calificaciones = $conexion->query($sql_calificaciones);

?>

<!DOCTYPE html>
<html lang="es">

<head>

    <meta charset="utf-8">

    <meta name="viewport" content="width=device-width, initial-scale=1">

    <link rel="stylesheet" href="styles.css">

    <title>Tablas Escolares</title>

</head>

<body>

<h1>Panel de Control Escolar</h1>


<!-- ================================= -->
<!-- TABLA ALUMNOS -->
<!-- ================================= -->

<h2>Tabla Alumnos</h2>

<div class="table-container">

    <table>

        <thead>

            <tr>

                <th>Alumno ID</th>
                <th>Nombre</th>
                <th>Apellido</th>
                <th>Fecha Nacimiento</th>
                <th>Teléfono</th>
                <th>Email</th>

            </tr>

        </thead>


        <tbody>

        <?php

        if ($resultado_alumnos && $resultado_alumnos->num_rows > 0) {

            while ($alumno = $resultado_alumnos->fetch_assoc()) {

        ?>

                <tr>

                    <td>
                        <?php echo htmlspecialchars($alumno['alumno_id']); ?>
                    </td>

                    <td>
                        <?php echo htmlspecialchars($alumno['nombre']); ?>
                    </td>

                    <td>
                        <?php echo htmlspecialchars($alumno['apellido']); ?>
                    </td>

                    <td>
                        <?php echo htmlspecialchars($alumno['fecha_nacimiento']); ?>
                    </td>

                    <td>
                        <?php echo htmlspecialchars($alumno['telefono']); ?>
                    </td>

                    <td>
                        <?php echo htmlspecialchars($alumno['email']); ?>
                    </td>

                </tr>

        <?php

            }

        } else {

            echo "<tr><td colspan='6'>No hay alumnos registrados.</td></tr>";

        }

        ?>

        </tbody>

    </table>

</div>


<!-- ================================= -->
<!-- TABLA COLEGIATURA -->
<!-- ================================= -->

<h2>Tabla Colegiatura</h2>

<div class="table-container">

    <table>

        <thead>

            <tr>

                <th>Colegiatura ID</th>
                <th>Alumno ID</th>
                <th>Monto</th>
                <th>Mes Pago</th>
                <th>Fecha Pago</th>
                <th>Estado Pago</th>

            </tr>

        </thead>


        <tbody>

        <?php

        if ($resultado_colegiaturas && $resultado_colegiaturas->num_rows > 0) {

            while ($colegiatura = $resultado_colegiaturas->fetch_assoc()) {

        ?>

                <tr>

                    <td>
                        <?php echo htmlspecialchars($colegiatura['colegiatura_id']); ?>
                    </td>

                    <td>
                        <?php echo htmlspecialchars($colegiatura['alumno_id']); ?>
                    </td>

                    <td>
                        $<?php echo number_format($colegiatura['monto'], 2); ?>
                    </td>

                    <td>
                        <?php echo htmlspecialchars($colegiatura['mes_pago']); ?>
                    </td>

                    <td>
                        <?php echo htmlspecialchars($colegiatura['fecha_pago']); ?>
                    </td>

                    <td>

                        <?php

                        if ($colegiatura['estado_pago'] == 'Pagado') {

                            echo '<span class="badge-pagado">Pagado</span>';

                        } else {

                            echo htmlspecialchars($colegiatura['estado_pago']);

                        }

                        ?>

                    </td>

                </tr>

        <?php

            }

        } else {

            echo "<tr><td colspan='6'>No hay colegiaturas registradas.</td></tr>";

        }

        ?>

        </tbody>

    </table>

</div>


<!-- ================================= -->
<!-- TABLA CALIFICACIONES -->
<!-- ================================= -->

<h2>Tabla Calificaciones</h2>

<div class="table-container">

    <table>

        <thead>

            <tr>

                <th>Calificación ID</th>
                <th>Alumno ID</th>
                <th>Materia</th>
                <th>Nota</th>
                <th>Periodo</th>

            </tr>

        </thead>


        <tbody>

        <?php

        if ($resultado_calificaciones && $resultado_calificaciones->num_rows > 0) {

            while ($calificacion = $resultado_calificaciones->fetch_assoc()) {

        ?>

                <tr>

                    <td>
                        <?php echo htmlspecialchars($calificacion['calificacion_id']); ?>
                    </td>

                    <td>
                        <?php echo htmlspecialchars($calificacion['alumno_id']); ?>
                    </td>

                    <td>
                        <?php echo htmlspecialchars($calificacion['materia']); ?>
                    </td>

                    <td>
                        <?php echo htmlspecialchars($calificacion['nota']); ?>
                    </td>

                    <td>
                        <?php echo htmlspecialchars($calificacion['periodo']); ?>
                    </td>

                </tr>

        <?php

            }

        } else {

            echo "<tr><td colspan='5'>No hay calificaciones registradas.</td></tr>";

        }

        ?>

        </tbody>

    </table>

</div>


</body>

</html>

<?php

$conexion->close();

?>
