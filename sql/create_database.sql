-- Execute as a MySQL administrator in MySQL Workbench or the mysql command line.
-- Use MySQL 8.4 or newer. Replace CHANGE_ME before executing this script.
CREATE DATABASE IF NOT EXISTS atelier_pc
    CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE USER IF NOT EXISTS 'atelier_pc'@'localhost' IDENTIFIED BY 'CHANGE_ME';
-- Synchronize the password even when the application account already exists.
ALTER USER 'atelier_pc'@'localhost' IDENTIFIED BY 'CHANGE_ME' ACCOUNT UNLOCK;
GRANT ALL PRIVILEGES ON atelier_pc.* TO 'atelier_pc'@'localhost';

-- Optional, only for running Django tests with this local development account:
-- GRANT ALL PRIVILEGES ON test_atelier_pc.* TO 'atelier_pc'@'localhost';
