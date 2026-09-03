-- MySQL dump 10.13  Distrib 8.0.45, for Win64 (x86_64)
--
-- Host: localhost    Database: escueladb
-- ------------------------------------------------------
-- Server version	8.0.46

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `calificaciones`
--

DROP TABLE IF EXISTS `calificaciones`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `calificaciones` (
  `calificacion_id` int NOT NULL,
  `alumno_id` int DEFAULT NULL,
  `materia` varchar(50) NOT NULL,
  `nota` decimal(4,2) NOT NULL,
  `periodo` varchar(20) DEFAULT NULL,
  PRIMARY KEY (`calificacion_id`),
  KEY `alumno_id` (`alumno_id`),
  CONSTRAINT `calificaciones_ibfk_1` FOREIGN KEY (`alumno_id`) REFERENCES `alumnos` (`alumno_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `calificaciones`
--

LOCK TABLES `calificaciones` WRITE;
/*!40000 ALTER TABLE `calificaciones` DISABLE KEYS */;
INSERT INTO `calificaciones` VALUES (1,1,'Educacion fisica',9.20,'2026-1'),(2,1,'Español',8.50,'2026-1'),(3,1,'Programación',9.80,'2026-1'),(4,1,'Inglés',8.90,'2026-1'),(5,1,'Física',8.20,'2026-1'),(6,2,'Educacion fisica',8.70,'2026-1'),(7,2,'Español',9.10,'2026-1'),(8,2,'Programación',8.80,'2026-1'),(9,2,'Inglés',9.30,'2026-1'),(16,4,'Educacion fisica',8.40,'2026-1'),(17,4,'Español',8.90,'2026-1'),(18,4,'Programación',9.10,'2026-1'),(19,4,'Inglés',8.70,'2026-1'),(22,5,'Español',8.50,'2026-1'),(23,5,'Programación',8.90,'2026-1'),(25,5,'Física',8.10,'2026-1'),(26,6,'Educacion fisica',9.50,'2026-1'),(27,6,'Español',9.00,'2026-1'),(28,6,'Programación',9.70,'2026-1'),(29,6,'Inglés',8.80,'2026-1'),(30,6,'Física',9.20,'2026-1'),(31,7,'Educacion fisica',8.70,'2026-1'),(32,7,'Español',8.30,'2026-1'),(33,7,'Programación',9.00,'2026-1'),(34,7,'Inglés',8.60,'2026-1'),(35,7,'Física',8.40,'2026-1'),(36,8,'Educacion fisica',9.10,'2026-1'),(37,8,'Español',9.20,'2026-1'),(38,8,'Programación',9.40,'2026-1'),(39,8,'Inglés',8.90,'2026-1'),(40,8,'Física',9.00,'2026-1'),(42,9,'Español',8.00,'2026-1'),(43,9,'Programación',8.50,'2026-1'),(45,9,'Física',8.20,'2026-1'),(51,11,'Educacion fisica',8.30,'2026-1'),(52,11,'Español',8.70,'2026-1'),(53,11,'Programación',9.20,'2026-1'),(54,11,'Inglés',8.40,'2026-1'),(55,11,'Física',8.60,'2026-1'),(61,13,'Educacion fisica',8.20,'2026-1'),(62,13,'Español',8.60,'2026-1'),(63,13,'Programación',9.00,'2026-1'),(64,13,'Inglés',8.30,'2026-1'),(65,13,'Física',8.70,'2026-1'),(66,14,'Educacion fisica',9.70,'2026-1'),(67,14,'Español',9.40,'2026-1'),(68,14,'Programación',9.80,'2026-1'),(69,14,'Inglés',9.50,'2026-1'),(70,14,'Física',9.20,'2026-1'),(72,15,'Español',8.20,'2026-1'),(73,15,'Programación',8.70,'2026-1'),(74,15,'Inglés',8.00,'2026-1'),(76,16,'Educacion fisica',8.80,'2026-1'),(77,16,'Español',9.00,'2026-1'),(78,16,'Programación',9.30,'2026-1'),(79,16,'Inglés',8.70,'2026-1'),(80,16,'Física',8.50,'2026-1'),(81,17,'Educacion fisica',9.40,'2026-1'),(82,17,'Español',8.90,'2026-1'),(83,17,'Programación',9.60,'2026-1'),(84,17,'Inglés',9.20,'2026-1'),(85,17,'Física',8.80,'2026-1'),(86,18,'Educacion fisica',8.60,'2026-1'),(87,18,'Español',8.40,'2026-1'),(88,18,'Programación',9.10,'2026-1'),(89,18,'Inglés',8.80,'2026-1'),(90,18,'Física',8.30,'2026-1'),(91,19,'Educacion fisica',9.30,'2026-1'),(92,19,'Español',9.00,'2026-1'),(93,19,'Programación',9.70,'2026-1'),(94,19,'Inglés',9.40,'2026-1'),(95,19,'Física',9.10,'2026-1'),(96,20,'Educacion fisica',8.10,'2026-1'),(97,20,'Español',8.50,'2026-1'),(98,20,'Programación',8.90,'2026-1'),(99,20,'Inglés',8.30,'2026-1'),(100,20,'Física',8.70,'2026-1');
/*!40000 ALTER TABLE `calificaciones` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-09-03  9:41:52
