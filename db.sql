-- Create database
CREATE DATABASE IF NOT EXISTS medchat CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE medchat;
ALTER TABLE users
ADD username VARCHAR(64) UNIQUE;
select *
from users;
-- USERS
CREATE TABLE IF NOT EXISTS users (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  username VARCHAR(64) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role ENUM('user', 'admin') NOT NULL DEFAULT 'user',
  is_verified TINYINT(1) NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  last_login_at DATETIME NULL
) ENGINE = InnoDB;

select * from user_sessions;
alter table user_sessions drop column user_agent, drop column ip;
CREATE TABLE IF NOT EXISTS user_sessions (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  refresh_token_hash CHAR(60) NOT NULL,
  user_agent VARCHAR(255),
  ip VARCHAR(45),
  expires_at DATETIME NOT NULL,
  revoked_at DATETIME NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  UNIQUE KEY uq_refresh_hash (refresh_token_hash),
  INDEX idx_user_exp (user_id, expires_at)
) ENGINE = InnoDB;

select *from conversations;
CREATE TABLE IF NOT EXISTS conversations (
  id VARCHAR(64) PRIMARY KEY,
  -- dùng currentId từ frontend
  user_id BIGINT NOT NULL,
  title VARCHAR(200),
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_conv_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  INDEX idx_user_time (user_id, updated_at)
) ENGINE = InnoDB;


select * from chat_messages;
CREATE TABLE IF NOT EXISTS chat_messages (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  convo_id VARCHAR(64) NOT NULL,
  user_id BIGINT NULL,
  role ENUM('user', 'user', 'system') NOT NULL,
  message_type ENUM('text', 'image') NOT NULL DEFAULT 'text',
  question LONGTEXT NULL,
  answer LONGTEXT NULL,
  image_path VARCHAR(255) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_msg_convo FOREIGN KEY (convo_id) REFERENCES conversations(id) ON DELETE CASCADE,
  CONSTRAINT fk_msg_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE
  SET NULL,
    INDEX idx_convo_created (convo_id, created_at)
) ENGINE = InnoDB;
