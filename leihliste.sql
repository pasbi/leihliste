SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";

CREATE TABLE `leihliste` (
  `loan_id` int(11) NOT NULL,
  `loan_name` varchar(255) NOT NULL,
  `start_date` datetime DEFAULT NULL,
  `end_date` datetime DEFAULT NULL,
  `borrower` varchar(255) DEFAULT NULL,
  `lender` varchar(255) DEFAULT NULL,
  `session_id` varchar(255) DEFAULT NULL,
  `acceptor` varchar(255) DEFAULT NULL,
  `notes` text DEFAULT NULL
) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

ALTER TABLE `leihliste`
  ADD PRIMARY KEY (`loan_id`);

ALTER TABLE `leihliste`
  MODIFY `loan_id` int(11) NOT NULL AUTO_INCREMENT;
COMMIT;
