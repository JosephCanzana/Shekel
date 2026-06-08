bash-5.1# cat schema.sql 
-- MySQL dump 10.13  Distrib 8.0.46, for Linux (x86_64)
--
-- Host: localhost    Database: shekel_db
-- ------------------------------------------------------
-- Server version       8.0.46

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `App_Settings`
--

DROP TABLE IF EXISTS `App_Settings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `App_Settings` (
  `id` int NOT NULL,
  `user_counter` int NOT NULL,
  `counter_year` int NOT NULL,
  `default_password` varchar(255) NOT NULL,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Audit_Log`
--

DROP TABLE IF EXISTS `Audit_Log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `Audit_Log` (
  `log_id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `action_type` enum('INSERT','UPDATE','DELETE','LOGIN','LOGOUT') NOT NULL,
  `module` enum('Products','Inventory','Sales','Defects','Users','Stock_In','Settings','Auth') NOT NULL,
  `reference_id` varchar(100) DEFAULT NULL,
  `reference_table` varchar(50) DEFAULT NULL,
  `description` text NOT NULL,
  `action_datetime` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`log_id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `Audit_Log_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `Users` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Categories`
--

DROP TABLE IF EXISTS `Categories`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `Categories` (
  `category_id` int NOT NULL AUTO_INCREMENT,
  `category_name` varchar(100) NOT NULL,
  `description` text,
  `status` varchar(20) NOT NULL,
  `default_low_stock_threshold` int NOT NULL,
  PRIMARY KEY (`category_id`),
  UNIQUE KEY `category_name` (`category_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Defect_Details`
--

DROP TABLE IF EXISTS `Defect_Details`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `Defect_Details` (
  `defect_detail_id` int NOT NULL AUTO_INCREMENT,
  `defect_id` int NOT NULL,
  `product_id` varchar(100) NOT NULL,
  `quantity` int NOT NULL,
  `origin` enum('in_store','customer') NOT NULL,
  `reason` enum('damaged','expired','change_of_mind') NOT NULL,
  `status` enum('submitted','active','rejected') NOT NULL,
  `customer_compensation` enum('full_refund','partial_refund','exchange_same','exchange_different','none') NOT NULL,
  `supplier_compensation` enum('pending','loss','same_item','different_item','money','none') NOT NULL,
  `exchange_product_id` varchar(100) DEFAULT NULL,
  `price_difference` decimal(10,2) DEFAULT NULL,
  `proposed_supplier_compensation` enum('loss','same_item','different_item','money') DEFAULT NULL,
  `cost_price_at_defect` decimal(10,2) NOT NULL,
  `revenue_price_at_defect` decimal(10,2) NOT NULL,
  `price_at_defect` decimal(10,2) NOT NULL,
  `subtotal_unit` decimal(10,2) NOT NULL,
  `subtotal_revenue` decimal(10,2) NOT NULL,
  `subtotal_amount` decimal(10,2) NOT NULL,
  `transaction_id` int DEFAULT NULL,
  `reviewed_by` int DEFAULT NULL,
  `reviewed_at` datetime DEFAULT NULL,
  `rejection_note` text,
  `is_archived` tinyint(1) NOT NULL,
  `archived_by` int DEFAULT NULL,
  `archived_at` datetime DEFAULT NULL,
  PRIMARY KEY (`defect_detail_id`),
  KEY `defect_id` (`defect_id`),
  KEY `product_id` (`product_id`),
  KEY `exchange_product_id` (`exchange_product_id`),
  KEY `transaction_id` (`transaction_id`),
  KEY `reviewed_by` (`reviewed_by`),
  KEY `archived_by` (`archived_by`),
  CONSTRAINT `Defect_Details_ibfk_1` FOREIGN KEY (`defect_id`) REFERENCES `Defects` (`defect_id`),
  CONSTRAINT `Defect_Details_ibfk_2` FOREIGN KEY (`product_id`) REFERENCES `Products` (`product_id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `Defect_Details_ibfk_3` FOREIGN KEY (`exchange_product_id`) REFERENCES `Products` (`product_id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `Defect_Details_ibfk_4` FOREIGN KEY (`transaction_id`) REFERENCES `Sales` (`transaction_id`) ON DELETE SET NULL,
  CONSTRAINT `Defect_Details_ibfk_5` FOREIGN KEY (`reviewed_by`) REFERENCES `Users` (`user_id`),
  CONSTRAINT `Defect_Details_ibfk_6` FOREIGN KEY (`archived_by`) REFERENCES `Users` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Defect_Exchange_Items`
--

DROP TABLE IF EXISTS `Defect_Exchange_Items`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `Defect_Exchange_Items` (
  `exchange_item_id` int NOT NULL AUTO_INCREMENT,
  `defect_detail_id` int NOT NULL,
  `product_id` varchar(100) NOT NULL,
  `quantity` int NOT NULL,
  `price_at_exchange` decimal(10,2) NOT NULL,
  `no_money_exchange` tinyint(1) NOT NULL,
  `override_used` tinyint(1) NOT NULL,
  PRIMARY KEY (`exchange_item_id`),
  KEY `defect_detail_id` (`defect_detail_id`),
  KEY `product_id` (`product_id`),
  CONSTRAINT `Defect_Exchange_Items_ibfk_1` FOREIGN KEY (`defect_detail_id`) REFERENCES `Defect_Details` (`defect_detail_id`) ON DELETE CASCADE,
  CONSTRAINT `Defect_Exchange_Items_ibfk_2` FOREIGN KEY (`product_id`) REFERENCES `Products` (`product_id`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Defects`
--

DROP TABLE IF EXISTS `Defects`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `Defects` (
  `defect_id` int NOT NULL AUTO_INCREMENT,
  `defect_datetime` datetime NOT NULL DEFAULT (now()),
  `user_id` int NOT NULL,
  `total_cost_price` decimal(10,2) NOT NULL,
  `total_revenue_price` decimal(10,2) NOT NULL,
  `total_amount` decimal(10,2) NOT NULL,
  `is_archived` tinyint(1) NOT NULL,
  `archived_by` int DEFAULT NULL,
  `archived_at` datetime DEFAULT NULL,
  PRIMARY KEY (`defect_id`),
  KEY `user_id` (`user_id`),
  KEY `archived_by` (`archived_by`),
  CONSTRAINT `Defects_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `Users` (`user_id`),
  CONSTRAINT `Defects_ibfk_2` FOREIGN KEY (`archived_by`) REFERENCES `Users` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Inventory`
--

DROP TABLE IF EXISTS `Inventory`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `Inventory` (
  `inventory_id` int NOT NULL AUTO_INCREMENT,
  `product_id` varchar(100) NOT NULL,
  `quantity_available` int NOT NULL,
  `quantity_defective` int NOT NULL,
  `last_updated` datetime NOT NULL,
  PRIMARY KEY (`inventory_id`),
  KEY `product_id` (`product_id`),
  CONSTRAINT `Inventory_ibfk_1` FOREIGN KEY (`product_id`) REFERENCES `Products` (`product_id`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ProductBundles`
--

DROP TABLE IF EXISTS `ProductBundles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ProductBundles` (
  `bundle_id` varchar(100) NOT NULL,
  `product_id` varchar(100) NOT NULL,
  `bundle_name` varchar(100) NOT NULL,
  `bundle_count` int NOT NULL,
  PRIMARY KEY (`bundle_id`),
  KEY `product_id` (`product_id`),
  CONSTRAINT `ProductBundles_ibfk_1` FOREIGN KEY (`product_id`) REFERENCES `Products` (`product_id`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Products`
--

DROP TABLE IF EXISTS `Products`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `Products` (
  `product_id` varchar(100) NOT NULL,
  `product_name` varchar(150) NOT NULL,
  `category_id` int DEFAULT NULL,
  `cost_price` decimal(10,2) NOT NULL,
  `revenue_price` decimal(10,2) NOT NULL,
  `total_price` decimal(10,2) NOT NULL,
  `low_reorder_threshold` int NOT NULL,
  `status` enum('active','archived') NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`product_id`),
  KEY `category_id` (`category_id`),
  CONSTRAINT `Products_ibfk_1` FOREIGN KEY (`category_id`) REFERENCES `Categories` (`category_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Recovery_Details`
--

DROP TABLE IF EXISTS `Recovery_Details`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `Recovery_Details` (
  `user_id` int NOT NULL,
  `email` varchar(100) NOT NULL,
  `phone_number` varchar(20) DEFAULT NULL,
  `is_verified` tinyint(1) NOT NULL,
  `verify_token` varchar(255) DEFAULT NULL,
  `verify_token_expiry` datetime DEFAULT NULL,
  `reset_token` varchar(255) DEFAULT NULL,
  `token_expiry` datetime DEFAULT NULL,
  PRIMARY KEY (`user_id`),
  CONSTRAINT `Recovery_Details_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `Users` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Role_Column_Settings`
--

DROP TABLE IF EXISTS `Role_Column_Settings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `Role_Column_Settings` (
  `id` int NOT NULL AUTO_INCREMENT,
  `role` varchar(50) NOT NULL,
  `page` varchar(50) NOT NULL,
  `available` text NOT NULL,
  `defaults` text NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Sales`
--

DROP TABLE IF EXISTS `Sales`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `Sales` (
  `transaction_id` int NOT NULL AUTO_INCREMENT,
  `sale_datetime` datetime NOT NULL DEFAULT (now()),
  `user_id` int NOT NULL,
  `total_cost_price` decimal(10,2) NOT NULL,
  `total_revenue_price` decimal(10,2) NOT NULL,
  `total_amount` decimal(10,2) NOT NULL,
  `payment_method` varchar(50) DEFAULT NULL,
  `tendered_amount` decimal(10,2) DEFAULT NULL,
  `change_amount` decimal(10,2) DEFAULT NULL,
  PRIMARY KEY (`transaction_id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `Sales_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `Users` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Sales_Details`
--

DROP TABLE IF EXISTS `Sales_Details`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `Sales_Details` (
  `sale_detail_id` int NOT NULL AUTO_INCREMENT,
  `transaction_id` int NOT NULL,
  `product_id` varchar(100) NOT NULL,
  `quantity` int NOT NULL,
  `cost_price_at_sale` decimal(10,2) NOT NULL,
  `revenue_price_at_sale` decimal(10,2) NOT NULL,
  `price_at_sale` decimal(10,2) NOT NULL,
  `subtotal_unit` decimal(10,2) NOT NULL,
  `subtotal_revenue` decimal(10,2) NOT NULL,
  `subtotal_amount` decimal(10,2) NOT NULL,
  `override_used` tinyint(1) NOT NULL,
  PRIMARY KEY (`sale_detail_id`),
  KEY `transaction_id` (`transaction_id`),
  KEY `product_id` (`product_id`),
  CONSTRAINT `Sales_Details_ibfk_1` FOREIGN KEY (`transaction_id`) REFERENCES `Sales` (`transaction_id`),
  CONSTRAINT `Sales_Details_ibfk_2` FOREIGN KEY (`product_id`) REFERENCES `Products` (`product_id`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Stock_Adjustment_Details`
--

DROP TABLE IF EXISTS `Stock_Adjustment_Details`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `Stock_Adjustment_Details` (
  `detail_id` int NOT NULL AUTO_INCREMENT,
  `request_id` int NOT NULL,
  `product_id` varchar(100) NOT NULL,
  `quantity_requested` int NOT NULL,
  `quantity_approved` int DEFAULT NULL,
  `status` enum('pending','approved','rejected') NOT NULL,
  `note` text,
  `rejection_reason` text,
  PRIMARY KEY (`detail_id`),
  KEY `request_id` (`request_id`),
  KEY `product_id` (`product_id`),
  CONSTRAINT `Stock_Adjustment_Details_ibfk_1` FOREIGN KEY (`request_id`) REFERENCES `Stock_Adjustment_Requests` (`request_id`) ON DELETE CASCADE,
  CONSTRAINT `Stock_Adjustment_Details_ibfk_2` FOREIGN KEY (`product_id`) REFERENCES `Products` (`product_id`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Stock_Adjustment_Requests`
--

DROP TABLE IF EXISTS `Stock_Adjustment_Requests`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `Stock_Adjustment_Requests` (
  `request_id` int NOT NULL AUTO_INCREMENT,
  `requested_by` int NOT NULL,
  `reviewed_by` int DEFAULT NULL,
  `submitted_at` datetime NOT NULL DEFAULT (now()),
  `reviewed_at` datetime DEFAULT NULL,
  `request_type` enum('stock_in','adjustment') NOT NULL,
  `status` enum('pending','approved','partially_approved','rejected') NOT NULL,
  PRIMARY KEY (`request_id`),
  KEY `requested_by` (`requested_by`),
  KEY `reviewed_by` (`reviewed_by`),
  CONSTRAINT `Stock_Adjustment_Requests_ibfk_1` FOREIGN KEY (`requested_by`) REFERENCES `Users` (`user_id`),
  CONSTRAINT `Stock_Adjustment_Requests_ibfk_2` FOREIGN KEY (`reviewed_by`) REFERENCES `Users` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Stock_In`
--

DROP TABLE IF EXISTS `Stock_In`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `Stock_In` (
  `stockin_id` int NOT NULL AUTO_INCREMENT,
  `batch_id` int DEFAULT NULL,
  `product_id` varchar(100) NOT NULL,
  `user_id` int NOT NULL,
  `quantity_received` int NOT NULL,
  `stockin_datetime` datetime NOT NULL DEFAULT (now()),
  `notes` text,
  PRIMARY KEY (`stockin_id`),
  KEY `product_id` (`product_id`),
  KEY `user_id` (`user_id`),
  KEY `ix_Stock_In_batch_id` (`batch_id`),
  CONSTRAINT `Stock_In_ibfk_1` FOREIGN KEY (`product_id`) REFERENCES `Products` (`product_id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `Stock_In_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `Users` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `User_Column_Preferences`
--

DROP TABLE IF EXISTS `User_Column_Preferences`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `User_Column_Preferences` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `page` varchar(50) NOT NULL,
  `columns` text NOT NULL,
  PRIMARY KEY (`id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `User_Column_Preferences_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `Users` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Users`
--

DROP TABLE IF EXISTS `Users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `Users` (
  `user_id` int NOT NULL,
  `first_name` varchar(50) NOT NULL,
  `last_name` varchar(50) NOT NULL,
  `role` enum('superadmin','admin','cashier','stocking') NOT NULL,
  `password` varchar(255) NOT NULL,
  `status` enum('activated','not_activated','suspended','archived') NOT NULL,
  PRIMARY KEY (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `maintenance_settings`
--

DROP TABLE IF EXISTS `maintenance_settings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `maintenance_settings` (
  `id` int NOT NULL AUTO_INCREMENT,
  `is_active` tinyint(1) NOT NULL,
  `scheduled_start` datetime DEFAULT NULL,
  `estimated_end` datetime DEFAULT NULL,
  `auto_end` tinyint(1) NOT NULL,
  `show_countdown` tinyint(1) NOT NULL,
  `message` text,
  `updated_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-06-08  7:53:16