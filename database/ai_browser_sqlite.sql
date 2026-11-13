ALTER TABLE ai_job ADD COLUMN input_kind VARCHAR(16) NOT NULL DEFAULT 'legacy';
CREATE TABLE IF NOT EXISTS "ai_browser_budget" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "key" VARCHAR(64) NOT NULL UNIQUE,
    "expires_at" TIMESTAMP NOT NULL,
    "sample_interval" INT NOT NULL  DEFAULT 10,
    "last_slot" BIGINT NOT NULL  DEFAULT -1,
    "last_claim_at" TIMESTAMP,
    "phase_ms" INT NOT NULL
) /* 课堂结束后清理的不可公开配额键；不关联结果或用户外键。 */;

CREATE TABLE IF NOT EXISTS "ai_browser_capture" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "capture_id" CHAR(36) NOT NULL UNIQUE,
    "active_key" VARCHAR(64)  UNIQUE,
    "token_hash" VARCHAR(64) NOT NULL,
    "expires_at" TIMESTAMP NOT NULL,
    "created_at" TIMESTAMP NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "stopped_at" TIMESTAMP,
    "last_slot" BIGINT NOT NULL  DEFAULT -1,
    "phase_ms" INT NOT NULL  DEFAULT 0,
    "job_id" BIGINT NOT NULL REFERENCES "ai_job" ("id") ON DELETE CASCADE,
    "owner_id" BIGINT REFERENCES "user" ("id") ON DELETE SET NULL
) /* 短期授权\/防重复控制信息；不在结果接口中暴露，不是学生结果归属。 */;

CREATE TABLE IF NOT EXISTS "ai_browser_frame" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "event_id" CHAR(36) NOT NULL UNIQUE,
    "generation" INT NOT NULL,
    "slot" BIGINT NOT NULL,
    "payload_hash" VARCHAR(64) NOT NULL,
    "captured_at" TIMESTAMP NOT NULL,
    "state" VARCHAR(16) NOT NULL  DEFAULT 'claimed',
    "reason" VARCHAR(32) NOT NULL  DEFAULT 'waiting',
    "counted" INT NOT NULL  DEFAULT 0,
    "inference_ms" REAL NOT NULL  DEFAULT 0,
    "capture_id" BIGINT REFERENCES "ai_browser_capture" ("id") ON DELETE SET NULL,
    "job_id" BIGINT NOT NULL REFERENCES "ai_job" ("id") ON DELETE CASCADE,
    "lease_id" BIGINT NOT NULL REFERENCES "ai_lease" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_ai_browser__capture_82ca86" UNIQUE ("capture_id", "slot")
) /* 仅短期元数据票据，不保存图片；防同一时间槽\/请求重复推理和入库。 */;
