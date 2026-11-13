-- Additive AI control/receipt tables; backup before applying.
CREATE TABLE IF NOT EXISTS `ai_device` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `created_at` DATETIME(6) NOT NULL  DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL  DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `name` VARCHAR(80) NOT NULL,
    `source_alias` VARCHAR(64) NOT NULL,
    `enabled` BOOL NOT NULL  DEFAULT 1,
    `last_seen` DATETIME(6),
    `incarnation` CHAR(36),
    `health` VARCHAR(32) NOT NULL  DEFAULT 'offline',
    `capabilities` JSON NOT NULL,
    KEY `idx_ai_device_created_ae686a` (`created_at`),
    KEY `idx_ai_device_updated_7c9af4` (`updated_at`)
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS `ai_credential` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `key_id` VARCHAR(32) NOT NULL UNIQUE,
    `secret_hash` VARCHAR(64) NOT NULL,
    `expires_at` DATETIME(6) NOT NULL,
    `revoked` BOOL NOT NULL  DEFAULT 0,
    `created_at` DATETIME(6) NOT NULL  DEFAULT CURRENT_TIMESTAMP(6),
    `device_id` BIGINT NOT NULL,
    CONSTRAINT `fk_ai_crede_ai_devic_521b1067` FOREIGN KEY (`device_id`) REFERENCES `ai_device` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS `ai_device_grant` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `device_id` BIGINT NOT NULL,
    `teacher_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_ai_device_g_device__6afe08` (`device_id`, `teacher_id`),
    CONSTRAINT `fk_ai_devic_ai_devic_7438fb4e` FOREIGN KEY (`device_id`) REFERENCES `ai_device` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_ai_devic_user_68e87dce` FOREIGN KEY (`teacher_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS `ai_job` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `created_at` DATETIME(6) NOT NULL  DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL  DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `request_id` CHAR(36) NOT NULL UNIQUE,
    `profile` VARCHAR(16) NOT NULL,
    `model_version` VARCHAR(64) NOT NULL,
    `mapping_version` VARCHAR(32) NOT NULL  DEFAULT 'five-emotions-v1',
    `threshold` DOUBLE NOT NULL,
    `detection_threshold` DOUBLE NOT NULL,
    `sample_interval` DOUBLE NOT NULL,
    `max_faces` INT NOT NULL  DEFAULT 10,
    `config_revision` INT NOT NULL  DEFAULT 1,
    `generation` INT NOT NULL  DEFAULT 1,
    `desired` VARCHAR(16) NOT NULL  DEFAULT 'ready',
    `observed` VARCHAR(16) NOT NULL  DEFAULT 'prechecking',
    `health` VARCHAR(32) NOT NULL  DEFAULT 'waiting',
    `metrics` JSON NOT NULL,
    `active_slot` VARCHAR(32)  UNIQUE,
    `last_ack` DATETIME(6),
    `started_at` DATETIME(6),
    `stopped_at` DATETIME(6),
    `creator_id` BIGINT,
    `device_id` BIGINT NOT NULL,
    `session_id` BIGINT NOT NULL,
    CONSTRAINT `fk_ai_job_user_e0feb820` FOREIGN KEY (`creator_id`) REFERENCES `user` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_ai_job_ai_devic_cd3a3487` FOREIGN KEY (`device_id`) REFERENCES `ai_device` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_ai_job_class_se_c748da21` FOREIGN KEY (`session_id`) REFERENCES `class_session` (`id`) ON DELETE CASCADE,
    KEY `idx_ai_job_created_f71ea1` (`created_at`),
    KEY `idx_ai_job_updated_8d8b30` (`updated_at`),
    KEY `idx_ai_job_session_b77f6c` (`session_id`, `created_at`)
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS `ai_lease` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `lease_id` CHAR(36) NOT NULL UNIQUE,
    `incarnation` CHAR(36) NOT NULL,
    `generation` INT NOT NULL,
    `acquired_at` DATETIME(6) NOT NULL,
    `expires_at` DATETIME(6) NOT NULL,
    `capture_end` DATETIME(6),
    `revoked` BOOL NOT NULL  DEFAULT 0,
    `credential_id` BIGINT NOT NULL,
    `job_id` BIGINT NOT NULL,
    UNIQUE KEY `uid_ai_lease_job_id_cafcb5` (`job_id`, `generation`),
    CONSTRAINT `fk_ai_lease_ai_crede_33a71c92` FOREIGN KEY (`credential_id`) REFERENCES `ai_credential` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_ai_lease_ai_job_c156e674` FOREIGN KEY (`job_id`) REFERENCES `ai_job` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS `ai_receipt` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `event_id` CHAR(36) NOT NULL UNIQUE,
    `payload_hash` VARCHAR(64) NOT NULL,
    `decision` VARCHAR(16) NOT NULL,
    `reason` VARCHAR(48) NOT NULL,
    `received_at` DATETIME(6) NOT NULL  DEFAULT CURRENT_TIMESTAMP(6),
    `job_id` BIGINT NOT NULL,
    `record_id` BIGINT,
    CONSTRAINT `fk_ai_recei_ai_job_5a57249b` FOREIGN KEY (`job_id`) REFERENCES `ai_job` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_ai_recei_emoji_re_f235d1e5` FOREIGN KEY (`record_id`) REFERENCES `emoji_record` (`id`) ON DELETE SET NULL,
    KEY `idx_ai_receipt_job_id_e91e2a` (`job_id`, `received_at`)
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS `ai_record_metadata` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `model_version` VARCHAR(64) NOT NULL,
    `mapping_version` VARCHAR(32) NOT NULL,
    `config_revision` INT NOT NULL,
    `quality` JSON NOT NULL,
    `job_id` BIGINT NOT NULL,
    `lease_id` BIGINT NOT NULL,
    `record_id` BIGINT NOT NULL UNIQUE,
    CONSTRAINT `fk_ai_recor_ai_job_45e685fc` FOREIGN KEY (`job_id`) REFERENCES `ai_job` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_ai_recor_ai_lease_6b020e9f` FOREIGN KEY (`lease_id`) REFERENCES `ai_lease` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_ai_recor_emoji_re_9dca4d00` FOREIGN KEY (`record_id`) REFERENCES `emoji_record` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
