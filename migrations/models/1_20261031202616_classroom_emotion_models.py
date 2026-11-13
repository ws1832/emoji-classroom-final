from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    if db and db.capabilities.dialect == "mysql":
        return "SELECT 1;"  # MySQL baseline tables are created by migration 0.
    return """
        CREATE TABLE IF NOT EXISTS "class_session" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "created_at" TIMESTAMP NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "start_time" TIMESTAMP NOT NULL  /* 开始时间 */,
    "end_time" TIMESTAMP NOT NULL  /* 结束时间 */,
    "classroom" VARCHAR(100)   /* 教室 */,
    "class_name" VARCHAR(100)   /* 班级 */,
    "course_id" BIGINT NOT NULL REFERENCES "course" ("id") ON DELETE CASCADE /* 课程ID */
) /* 课程的一次课堂会话。 */;
CREATE INDEX IF NOT EXISTS "idx_class_sessi_created_38af0a" ON "class_session" ("created_at");
CREATE INDEX IF NOT EXISTS "idx_class_sessi_updated_8ab12b" ON "class_session" ("updated_at");
CREATE INDEX IF NOT EXISTS "idx_class_sessi_start_t_dfa305" ON "class_session" ("start_time");
CREATE INDEX IF NOT EXISTS "idx_class_sessi_end_tim_17f41c" ON "class_session" ("end_time");
CREATE INDEX IF NOT EXISTS "idx_class_sessi_course__d8f73b" ON "class_session" ("course_id");
CREATE INDEX IF NOT EXISTS "idx_class_sessi_course__ab0726" ON "class_session" ("course_id", "start_time");
        CREATE TABLE IF NOT EXISTS "course" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "created_at" TIMESTAMP NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "name" VARCHAR(100) NOT NULL  /* 课程名称 */,
    "description" VARCHAR(500)   /* 课程描述 */,
    "teacher_id" BIGINT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE /* 教师ID */,
    CONSTRAINT "uid_course_name_dbcf51" UNIQUE ("name", "teacher_id")
) /* 一门由教师负责的课程。 */;
CREATE INDEX IF NOT EXISTS "idx_course_created_eae14b" ON "course" ("created_at");
CREATE INDEX IF NOT EXISTS "idx_course_updated_366ffe" ON "course" ("updated_at");
CREATE INDEX IF NOT EXISTS "idx_course_name_3ad36f" ON "course" ("name");
CREATE INDEX IF NOT EXISTS "idx_course_teacher_81a272" ON "course" ("teacher_id");
        CREATE TABLE IF NOT EXISTS "emoji_record" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "emoji_type" VARCHAR(32) NOT NULL  /* Emoji类型 */,
    "timestamp" TIMESTAMP NOT NULL  DEFAULT CURRENT_TIMESTAMP /* 记录时间 */,
    "source" VARCHAR(10) NOT NULL  DEFAULT 'MANUAL' /* 记录来源 */,
    "confidence" REAL   /* AI置信度 */,
    "device_source" VARCHAR(100)   /* 设备来源 */,
    "session_id" BIGINT NOT NULL REFERENCES "class_session" ("id") ON DELETE CASCADE /* 课堂会话ID */,
    "user_id" BIGINT REFERENCES "user" ("id") ON DELETE SET NULL /* 用户ID */
) /* 学生手动或 AI 生成的一条情绪记录。 */;
CREATE INDEX IF NOT EXISTS "idx_emoji_recor_emoji_t_4f5e53" ON "emoji_record" ("emoji_type");
CREATE INDEX IF NOT EXISTS "idx_emoji_recor_timesta_5a5215" ON "emoji_record" ("timestamp");
CREATE INDEX IF NOT EXISTS "idx_emoji_recor_source_aa1449" ON "emoji_record" ("source");
CREATE INDEX IF NOT EXISTS "idx_emoji_recor_session_024140" ON "emoji_record" ("session_id");
CREATE INDEX IF NOT EXISTS "idx_emoji_recor_user_id_8a4fa7" ON "emoji_record" ("user_id");
CREATE INDEX IF NOT EXISTS "idx_emoji_recor_session_d3c4fb" ON "emoji_record" ("session_id", "timestamp");
CREATE INDEX IF NOT EXISTS "idx_emoji_recor_user_id_5b865a" ON "emoji_record" ("user_id", "timestamp");
CREATE INDEX IF NOT EXISTS "idx_emoji_recor_source_0d0840" ON "emoji_record" ("source", "timestamp");
        CREATE TABLE IF NOT EXISTS "schedule_user" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "created_at" TIMESTAMP NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "scheduled_at" TIMESTAMP NOT NULL  DEFAULT CURRENT_TIMESTAMP /* 安排时间 */,
    "session_id" BIGINT NOT NULL REFERENCES "class_session" ("id") ON DELETE CASCADE /* 课堂会话ID */,
    "user_id" BIGINT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE /* 用户ID */,
    CONSTRAINT "uid_schedule_us_session_3665c2" UNIQUE ("session_id", "user_id")
) /* 课堂会话中的用户排课关系。 */;
CREATE INDEX IF NOT EXISTS "idx_schedule_us_created_4dd762" ON "schedule_user" ("created_at");
CREATE INDEX IF NOT EXISTS "idx_schedule_us_updated_1063e6" ON "schedule_user" ("updated_at");
CREATE INDEX IF NOT EXISTS "idx_schedule_us_schedul_36d55c" ON "schedule_user" ("scheduled_at");
CREATE INDEX IF NOT EXISTS "idx_schedule_us_session_f103ca" ON "schedule_user" ("session_id");
CREATE INDEX IF NOT EXISTS "idx_schedule_us_user_id_c4d0fc" ON "schedule_user" ("user_id");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "schedule_user";
        DROP TABLE IF EXISTS "course";
        DROP TABLE IF EXISTS "class_session";
        DROP TABLE IF EXISTS "emoji_record";"""
