ALTER TABLE ai_job ADD COLUMN input_kind VARCHAR(16) NOT NULL DEFAULT 'legacy';
CREATE TABLE IF NOT EXISTS `ai_browser_budget` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `key` VARCHAR(64) NOT NULL UNIQUE,
    `expires_at` DATETIME(6) NOT NULL,
    `sample_interval` INT NOT NULL  DEFAULT 10,
    `last_slot` BIGINT NOT NULL  DEFAULT -1,
    `last_claim_at` DATETIME(6),
    `phase_ms` INT NOT NULL
) CHARACTER SET utf8mb4 COMMENT='课堂结束后清理的不可公开配额键；不关联结果或用户外键。';

CREATE TABLE IF NOT EXISTS `ai_browser_capture` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `capture_id` CHAR(36) NOT NULL UNIQUE,
    `active_key` VARCHAR(64)  UNIQUE,
    `token_hash` VARCHAR(64) NOT NULL,
    `expires_at` DATETIME(6) NOT NULL,
    `created_at` DATETIME(6) NOT NULL  DEFAULT CURRENT_TIMESTAMP(6),
    `stopped_at` DATETIME(6),
    `last_slot` BIGINT NOT NULL  DEFAULT -1,
    `phase_ms` INT NOT NULL  DEFAULT 0,
    `job_id` BIGINT NOT NULL,
    `owner_id` BIGINT,
    CONSTRAINT `fk_ai_brows_ai_job_d997d4b7` FOREIGN KEY (`job_id`) REFERENCES `ai_job` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_ai_brows_user_46d7c559` FOREIGN KEY (`owner_id`) REFERENCES `user` (`id`) ON DELETE SET NULL
) CHARACTER SET utf8mb4 COMMENT='短期授权/防重复控制信息；不在结果接口中暴露，不是学生结果归属。';

CREATE TABLE IF NOT EXISTS `ai_browser_frame` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `event_id` CHAR(36) NOT NULL UNIQUE,
    `generation` INT NOT NULL,
    `slot` BIGINT NOT NULL,
    `payload_hash` VARCHAR(64) NOT NULL,
    `captured_at` DATETIME(6) NOT NULL,
    `state` VARCHAR(16) NOT NULL  DEFAULT 'claimed',
    `reason` VARCHAR(32) NOT NULL  DEFAULT 'waiting',
    `counted` BOOL NOT NULL  DEFAULT 0,
    `inference_ms` DOUBLE NOT NULL  DEFAULT 0,
    `capture_id` BIGINT,
    `job_id` BIGINT NOT NULL,
    `lease_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_ai_browser__capture_82ca86` (`capture_id`, `slot`),
    CONSTRAINT `fk_ai_brows_ai_brows_a815cb08` FOREIGN KEY (`capture_id`) REFERENCES `ai_browser_capture` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_ai_brows_ai_job_a91562a9` FOREIGN KEY (`job_id`) REFERENCES `ai_job` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_ai_brows_ai_lease_75fc1339` FOREIGN KEY (`lease_id`) REFERENCES `ai_lease` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='仅短期元数据票据，不保存图片；防同一时间槽/请求重复推理和入库。';
