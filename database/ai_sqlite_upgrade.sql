-- Additive AI control/receipt tables; backup before applying.
CREATE TABLE IF NOT EXISTS "ai_device" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "created_at" TIMESTAMP NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "name" VARCHAR(80) NOT NULL,
    "source_alias" VARCHAR(64) NOT NULL,
    "enabled" INT NOT NULL  DEFAULT 1,
    "last_seen" TIMESTAMP,
    "incarnation" CHAR(36),
    "health" VARCHAR(32) NOT NULL  DEFAULT 'offline',
    "capabilities" JSON NOT NULL
);
CREATE INDEX IF NOT EXISTS "idx_ai_device_created_ae686a" ON "ai_device" ("created_at");
CREATE INDEX IF NOT EXISTS "idx_ai_device_updated_7c9af4" ON "ai_device" ("updated_at");

CREATE TABLE IF NOT EXISTS "ai_credential" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "key_id" VARCHAR(32) NOT NULL UNIQUE,
    "secret_hash" VARCHAR(64) NOT NULL,
    "expires_at" TIMESTAMP NOT NULL,
    "revoked" INT NOT NULL  DEFAULT 0,
    "created_at" TIMESTAMP NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "device_id" BIGINT NOT NULL REFERENCES "ai_device" ("id") ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS "ai_device_grant" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "device_id" BIGINT NOT NULL REFERENCES "ai_device" ("id") ON DELETE CASCADE,
    "teacher_id" BIGINT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_ai_device_g_device__6afe08" UNIQUE ("device_id", "teacher_id")
);

CREATE TABLE IF NOT EXISTS "ai_job" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "created_at" TIMESTAMP NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "request_id" CHAR(36) NOT NULL UNIQUE,
    "profile" VARCHAR(16) NOT NULL,
    "model_version" VARCHAR(64) NOT NULL,
    "mapping_version" VARCHAR(32) NOT NULL  DEFAULT 'five-emotions-v1',
    "threshold" REAL NOT NULL,
    "detection_threshold" REAL NOT NULL,
    "sample_interval" REAL NOT NULL,
    "max_faces" INT NOT NULL  DEFAULT 10,
    "config_revision" INT NOT NULL  DEFAULT 1,
    "generation" INT NOT NULL  DEFAULT 1,
    "desired" VARCHAR(16) NOT NULL  DEFAULT 'ready',
    "observed" VARCHAR(16) NOT NULL  DEFAULT 'prechecking',
    "health" VARCHAR(32) NOT NULL  DEFAULT 'waiting',
    "metrics" JSON NOT NULL,
    "active_slot" VARCHAR(32)  UNIQUE,
    "last_ack" TIMESTAMP,
    "started_at" TIMESTAMP,
    "stopped_at" TIMESTAMP,
    "creator_id" BIGINT REFERENCES "user" ("id") ON DELETE SET NULL,
    "device_id" BIGINT NOT NULL REFERENCES "ai_device" ("id") ON DELETE CASCADE,
    "session_id" BIGINT NOT NULL REFERENCES "class_session" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_ai_job_created_f71ea1" ON "ai_job" ("created_at");
CREATE INDEX IF NOT EXISTS "idx_ai_job_updated_8d8b30" ON "ai_job" ("updated_at");
CREATE INDEX IF NOT EXISTS "idx_ai_job_session_b77f6c" ON "ai_job" ("session_id", "created_at");

CREATE TABLE IF NOT EXISTS "ai_lease" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "lease_id" CHAR(36) NOT NULL UNIQUE,
    "incarnation" CHAR(36) NOT NULL,
    "generation" INT NOT NULL,
    "acquired_at" TIMESTAMP NOT NULL,
    "expires_at" TIMESTAMP NOT NULL,
    "capture_end" TIMESTAMP,
    "revoked" INT NOT NULL  DEFAULT 0,
    "credential_id" BIGINT NOT NULL REFERENCES "ai_credential" ("id") ON DELETE CASCADE,
    "job_id" BIGINT NOT NULL REFERENCES "ai_job" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_ai_lease_job_id_cafcb5" UNIQUE ("job_id", "generation")
);

CREATE TABLE IF NOT EXISTS "ai_receipt" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "event_id" CHAR(36) NOT NULL UNIQUE,
    "payload_hash" VARCHAR(64) NOT NULL,
    "decision" VARCHAR(16) NOT NULL,
    "reason" VARCHAR(48) NOT NULL,
    "received_at" TIMESTAMP NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "job_id" BIGINT NOT NULL REFERENCES "ai_job" ("id") ON DELETE CASCADE,
    "record_id" BIGINT REFERENCES "emoji_record" ("id") ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS "idx_ai_receipt_job_id_e91e2a" ON "ai_receipt" ("job_id", "received_at");

CREATE TABLE IF NOT EXISTS "ai_record_metadata" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "model_version" VARCHAR(64) NOT NULL,
    "mapping_version" VARCHAR(32) NOT NULL,
    "config_revision" INT NOT NULL,
    "quality" JSON NOT NULL,
    "job_id" BIGINT NOT NULL REFERENCES "ai_job" ("id") ON DELETE CASCADE,
    "lease_id" BIGINT NOT NULL REFERENCES "ai_lease" ("id") ON DELETE CASCADE,
    "record_id" BIGINT NOT NULL UNIQUE REFERENCES "emoji_record" ("id") ON DELETE CASCADE
);
