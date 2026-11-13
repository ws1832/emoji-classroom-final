-- 表情符号课堂情绪检查器系统 MySQL 建表脚本。
-- 历史手写结构参考，非当前安装/升级入口。当前运行 scripts/migrate.py 应用提交迁移0→1→2→3。
-- 不要在此脚本建库后直接混跑Aerich；既有库先进行ORM字段与迁移历史核对。
-- 使用前请确认 MySQL 版本为 8.0.16 或更高版本，以便启用 CHECK 约束。
-- 本脚本不保存原始视频或人脸图片，只保存结构化情绪结果。

CREATE DATABASE IF NOT EXISTS `emoji_classroom`
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE `emoji_classroom`;

-- 关闭外键检查：脚本可能被工具分段或单条执行，先关闭外键校验，
-- 避免引用表尚未创建时出现 Error 1824（Failed to open the referenced table）。
SET FOREIGN_KEY_CHECKS = 0;

-- 用户表：密码字段只能保存 Argon2 等加盐哈希，禁止保存明文密码。
CREATE TABLE IF NOT EXISTS `user` (
    `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '用户ID',
    `username` VARCHAR(20) NOT NULL COMMENT '用户名',
    `user_no` VARCHAR(16) NULL COMMENT '用户编号（学生 PBxxxx、教师 TBxxxx）',
    `alias` VARCHAR(30) NULL COMMENT '姓名',
    `email` VARCHAR(255) NOT NULL COMMENT '邮箱',
    `phone` VARCHAR(20) NULL COMMENT '电话',
    `password` VARCHAR(128) NOT NULL COMMENT '加盐密码哈希',
    `is_active` BOOLEAN NOT NULL DEFAULT TRUE COMMENT '是否激活',
    `is_superuser` BOOLEAN NOT NULL DEFAULT FALSE COMMENT '是否为超级管理员',
    `last_login` DATETIME NULL COMMENT '最后登录时间',
    `dept_id` BIGINT NULL COMMENT '部门ID',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_user_username` (`username`),
    UNIQUE KEY `uk_user_user_no` (`user_no`),
    UNIQUE KEY `uk_user_email` (`email`),
    KEY `idx_user_alias` (`alias`),
    KEY `idx_user_phone` (`phone`),
    KEY `idx_user_active` (`is_active`),
    KEY `idx_user_superuser` (`is_superuser`),
    KEY `idx_user_dept` (`dept_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='系统用户表';

-- 角色表和用户角色关联表：满足指导书中的 RBAC 要求。
CREATE TABLE IF NOT EXISTS `role` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `name` VARCHAR(20) NOT NULL COMMENT '角色名称',
    `desc` VARCHAR(500) NULL COMMENT '角色描述',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_role_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='系统角色表';

CREATE TABLE IF NOT EXISTS `user_role` (
    `user_id` BIGINT NOT NULL,
    `role_id` BIGINT NOT NULL,
    PRIMARY KEY (`user_id`, `role_id`),
    CONSTRAINT `fk_user_role_user`
        FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_user_role_role`
        FOREIGN KEY (`role_id`) REFERENCES `role` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='用户角色关联表';

-- 以下是原模板的权限和组织结构兼容表。
-- 它们不是实验核心实体，但当前 init_app.py 会初始化并使用它们。
CREATE TABLE IF NOT EXISTS `api` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `path` VARCHAR(100) NOT NULL COMMENT 'API路径',
    `method` VARCHAR(6) NOT NULL COMMENT '请求方法',
    `summary` VARCHAR(500) NOT NULL COMMENT '请求简介',
    `tags` VARCHAR(100) NOT NULL COMMENT 'API标签',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_api_path` (`path`),
    KEY `idx_api_method` (`method`),
    KEY `idx_api_tags` (`tags`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='模板接口权限表';

CREATE TABLE IF NOT EXISTS `menu` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `name` VARCHAR(20) NOT NULL COMMENT '菜单名称',
    `remark` JSON NULL COMMENT '保留字段',
    `menu_type` VARCHAR(7) NULL COMMENT '菜单类型',
    `icon` VARCHAR(100) NULL COMMENT '菜单图标',
    `path` VARCHAR(100) NOT NULL COMMENT '菜单路径',
    `order` INT NOT NULL DEFAULT 0 COMMENT '排序',
    `parent_id` BIGINT NOT NULL DEFAULT 0 COMMENT '父菜单ID',
    `is_hidden` BOOLEAN NOT NULL DEFAULT FALSE COMMENT '是否隐藏',
    `component` VARCHAR(100) NOT NULL COMMENT '组件',
    `keepalive` BOOLEAN NOT NULL DEFAULT TRUE COMMENT '是否缓存',
    `redirect` VARCHAR(100) NULL COMMENT '重定向地址',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_menu_path` (`path`),
    KEY `idx_menu_parent` (`parent_id`),
    KEY `idx_menu_order` (`order`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='模板菜单表';

CREATE TABLE IF NOT EXISTS `dept` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `name` VARCHAR(20) NOT NULL COMMENT '部门名称',
    `desc` VARCHAR(500) NULL COMMENT '备注',
    `is_deleted` BOOLEAN NOT NULL DEFAULT FALSE COMMENT '是否删除',
    `order` INT NOT NULL DEFAULT 0 COMMENT '排序',
    `parent_id` BIGINT NOT NULL DEFAULT 0 COMMENT '父部门ID',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_dept_name` (`name`),
    KEY `idx_dept_parent` (`parent_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='模板部门表';

CREATE TABLE IF NOT EXISTS `deptclosure` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `ancestor` BIGINT NOT NULL COMMENT '父代部门ID',
    `descendant` BIGINT NOT NULL COMMENT '后代部门ID',
    `level` INT NOT NULL DEFAULT 0 COMMENT '层级',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_deptclosure_ancestor` (`ancestor`),
    KEY `idx_deptclosure_descendant` (`descendant`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='模板部门闭包表';

CREATE TABLE IF NOT EXISTS `role_menu` (
    `role_id` BIGINT NOT NULL,
    `menu_id` BIGINT NOT NULL,
    PRIMARY KEY (`role_id`, `menu_id`),
    CONSTRAINT `fk_role_menu_role`
        FOREIGN KEY (`role_id`) REFERENCES `role` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_role_menu_menu`
        FOREIGN KEY (`menu_id`) REFERENCES `menu` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='角色菜单关联表';

CREATE TABLE IF NOT EXISTS `role_api` (
    `role_id` BIGINT NOT NULL,
    `api_id` BIGINT NOT NULL,
    PRIMARY KEY (`role_id`, `api_id`),
    CONSTRAINT `fk_role_api_role`
        FOREIGN KEY (`role_id`) REFERENCES `role` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_role_api_api`
        FOREIGN KEY (`api_id`) REFERENCES `api` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='角色接口关联表';

-- Aerich 版本记录表：使用项目启动时的数据库迁移功能时需要。
CREATE TABLE IF NOT EXISTS `aerich` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `version` VARCHAR(255) NOT NULL,
    `app` VARCHAR(100) NOT NULL,
    `content` JSON NOT NULL,
    PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Aerich迁移版本表';

-- 审计日志是指导书建议的实体，记录登录、导出和权限变更等操作。
CREATE TABLE IF NOT EXISTS `auditlog` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    `user_id` BIGINT NOT NULL,
    `username` VARCHAR(64) NOT NULL DEFAULT '',
    `module` VARCHAR(64) NOT NULL DEFAULT '',
    `summary` VARCHAR(128) NOT NULL DEFAULT '',
    `method` VARCHAR(10) NOT NULL DEFAULT '',
    `path` VARCHAR(255) NOT NULL DEFAULT '',
    `status` INT NOT NULL DEFAULT -1,
    `response_time` INT NOT NULL DEFAULT 0 COMMENT '响应时间，单位毫秒',
    `request_args` JSON NULL,
    `response_body` JSON NULL,
    PRIMARY KEY (`id`),
    KEY `idx_auditlog_user` (`user_id`),
    KEY `idx_auditlog_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='关键操作审计日志';

-- 课程表：一门由教师负责的课程。
CREATE TABLE IF NOT EXISTS `course` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    `name` VARCHAR(100) NOT NULL COMMENT '课程名称',
    `description` VARCHAR(500) NULL COMMENT '课程描述',
    `teacher_id` BIGINT NOT NULL COMMENT '教师ID',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_course_name_teacher` (`name`, `teacher_id`),
    KEY `idx_course_name` (`name`),
    KEY `idx_course_teacher` (`teacher_id`),
    CONSTRAINT `fk_course_teacher`
        FOREIGN KEY (`teacher_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='课程表';

-- 课堂会话表：同一课程可以有多次课堂会话。
CREATE TABLE IF NOT EXISTS `class_session` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    `course_id` BIGINT NOT NULL COMMENT '课程ID',
    `start_time` DATETIME NOT NULL COMMENT '开始时间',
    `end_time` DATETIME NOT NULL COMMENT '结束时间',
    `classroom` VARCHAR(100) NULL COMMENT '教室',
    `class_name` VARCHAR(100) NULL COMMENT '班级',
    PRIMARY KEY (`id`),
    KEY `idx_session_course` (`course_id`),
    KEY `idx_session_start` (`start_time`),
    KEY `idx_session_course_start` (`course_id`, `start_time`),
    CONSTRAINT `fk_session_course`
        FOREIGN KEY (`course_id`) REFERENCES `course` (`id`) ON DELETE CASCADE,
    CONSTRAINT `chk_session_time`
        CHECK (`end_time` > `start_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='课堂会话表';

-- 排课表：记录某个用户是否被安排到某次课堂。
CREATE TABLE IF NOT EXISTS `schedule_user` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    `scheduled_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '安排时间',
    `session_id` BIGINT NOT NULL COMMENT '课堂会话ID',
    `user_id` BIGINT NOT NULL COMMENT '用户ID',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_schedule_session_user` (`session_id`, `user_id`),
    KEY `idx_schedule_session` (`session_id`),
    KEY `idx_schedule_user` (`user_id`),
    CONSTRAINT `fk_schedule_session`
        FOREIGN KEY (`session_id`) REFERENCES `class_session` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_schedule_user`
        FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='课堂用户排课表';

-- Emoji 情绪记录表。
-- AI 记录可以匿名，但必须包含 session_id、source=AI 和 confidence。
-- 原始视频、人脸图片不在本表中保存。
CREATE TABLE IF NOT EXISTS `emoji_record` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `user_id` BIGINT NULL COMMENT '用户ID，AI匿名记录可以为空',
    `session_id` BIGINT NOT NULL COMMENT '课堂会话ID',
    `emoji_type` VARCHAR(32) NOT NULL COMMENT '情绪类型',
    `timestamp` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录时间',
    `source` VARCHAR(10) NOT NULL DEFAULT 'MANUAL' COMMENT 'MANUAL或AI',
    `confidence` DOUBLE NULL COMMENT 'AI置信度，范围0到1',
    `device_source` VARCHAR(100) NULL COMMENT '设备或来源标识',
    PRIMARY KEY (`id`),
    KEY `idx_emoji_user_time` (`user_id`, `timestamp`),
    KEY `idx_emoji_session_time` (`session_id`, `timestamp`),
    KEY `idx_emoji_source_time` (`source`, `timestamp`),
    CONSTRAINT `fk_emoji_user`
        FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_emoji_session`
        FOREIGN KEY (`session_id`) REFERENCES `class_session` (`id`) ON DELETE CASCADE,
    CONSTRAINT `chk_emoji_type`
        CHECK (`emoji_type` IN ('HAPPY', 'SAD', 'ANGRY', 'SURPRISED', 'NEUTRAL')),
    CONSTRAINT `chk_emoji_source`
        CHECK (`source` IN ('MANUAL', 'AI')),
    CONSTRAINT `chk_emoji_confidence_range`
        CHECK (`confidence` IS NULL OR (`confidence` >= 0 AND `confidence` <= 1)),
    CONSTRAINT `chk_ai_confidence`
        CHECK (`source` <> 'AI' OR `confidence` IS NOT NULL),
    CONSTRAINT `chk_manual_confidence`
        CHECK (`source` <> 'MANUAL' OR `confidence` IS NULL)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='课堂 Emoji 情绪记录表';

-- 恢复外键检查，保证后续增删改数据时外键约束仍然生效。
SET FOREIGN_KEY_CHECKS = 1;
