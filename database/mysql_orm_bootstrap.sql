-- ORM-compatible bootstrap for Aerich deployments.
CREATE TABLE IF NOT EXISTS `api` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `created_at` DATETIME(6) NOT NULL  DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL  DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `path` VARCHAR(100) NOT NULL  COMMENT 'API路径',
    `method` VARCHAR(6) NOT NULL  COMMENT '请求方法',
    `summary` VARCHAR(500) NOT NULL  COMMENT '请求简介',
    `tags` VARCHAR(100) NOT NULL  COMMENT 'API标签',
    KEY `idx_api_created_78d19f` (`created_at`),
    KEY `idx_api_updated_643c8b` (`updated_at`),
    KEY `idx_api_path_9ed611` (`path`),
    KEY `idx_api_method_a46dfb` (`method`),
    KEY `idx_api_summary_400f73` (`summary`),
    KEY `idx_api_tags_04ae27` (`tags`)
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS `auditlog` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `created_at` DATETIME(6) NOT NULL  DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL  DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `user_id` INT NOT NULL  COMMENT '用户ID',
    `username` VARCHAR(64) NOT NULL  COMMENT '用户名称' DEFAULT '',
    `module` VARCHAR(64) NOT NULL  COMMENT '功能模块' DEFAULT '',
    `summary` VARCHAR(128) NOT NULL  COMMENT '请求描述' DEFAULT '',
    `method` VARCHAR(10) NOT NULL  COMMENT '请求方法' DEFAULT '',
    `path` VARCHAR(255) NOT NULL  COMMENT '请求路径' DEFAULT '',
    `status` INT NOT NULL  COMMENT '状态码' DEFAULT -1,
    `response_time` INT NOT NULL  COMMENT '响应时间(单位ms)' DEFAULT 0,
    `request_args` JSON   COMMENT '请求参数',
    `response_body` JSON   COMMENT '返回数据',
    KEY `idx_auditlog_created_cc33d0` (`created_at`),
    KEY `idx_auditlog_updated_2f871f` (`updated_at`),
    KEY `idx_auditlog_user_id_4b93fa` (`user_id`),
    KEY `idx_auditlog_usernam_b187b3` (`username`),
    KEY `idx_auditlog_module_04058b` (`module`),
    KEY `idx_auditlog_summary_3e27da` (`summary`),
    KEY `idx_auditlog_method_4270a2` (`method`),
    KEY `idx_auditlog_path_b99502` (`path`),
    KEY `idx_auditlog_status_2a72d2` (`status`),
    KEY `idx_auditlog_respons_8caa87` (`response_time`)
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS `dept` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `created_at` DATETIME(6) NOT NULL  DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL  DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `name` VARCHAR(20) NOT NULL UNIQUE COMMENT '部门名称',
    `desc` VARCHAR(500)   COMMENT '备注',
    `is_deleted` BOOL NOT NULL  COMMENT '软删除标记' DEFAULT 0,
    `order` INT NOT NULL  COMMENT '排序' DEFAULT 0,
    `parent_id` INT NOT NULL  COMMENT '父部门ID' DEFAULT 0,
    KEY `idx_dept_created_4b11cf` (`created_at`),
    KEY `idx_dept_updated_0c0bd1` (`updated_at`),
    KEY `idx_dept_name_c2b9da` (`name`),
    KEY `idx_dept_is_dele_466228` (`is_deleted`),
    KEY `idx_dept_order_ddabe1` (`order`),
    KEY `idx_dept_parent__a71a57` (`parent_id`)
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS `deptclosure` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `created_at` DATETIME(6) NOT NULL  DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL  DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `ancestor` INT NOT NULL  COMMENT '父代',
    `descendant` INT NOT NULL  COMMENT '子代',
    `level` INT NOT NULL  COMMENT '深度' DEFAULT 0,
    KEY `idx_deptclosure_created_96f6ef` (`created_at`),
    KEY `idx_deptclosure_updated_41fc08` (`updated_at`),
    KEY `idx_deptclosure_ancesto_fbc4ce` (`ancestor`),
    KEY `idx_deptclosure_descend_2ae8b1` (`descendant`),
    KEY `idx_deptclosure_level_ae16b2` (`level`)
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS `menu` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `created_at` DATETIME(6) NOT NULL  DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL  DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `name` VARCHAR(20) NOT NULL  COMMENT '菜单名称',
    `remark` JSON   COMMENT '保留字段',
    `menu_type` VARCHAR(7)   COMMENT '菜单类型',
    `icon` VARCHAR(100)   COMMENT '菜单图标',
    `path` VARCHAR(100) NOT NULL  COMMENT '菜单路径',
    `order` INT NOT NULL  COMMENT '排序' DEFAULT 0,
    `parent_id` INT NOT NULL  COMMENT '父菜单ID' DEFAULT 0,
    `is_hidden` BOOL NOT NULL  COMMENT '是否隐藏' DEFAULT 0,
    `component` VARCHAR(100) NOT NULL  COMMENT '组件',
    `keepalive` BOOL NOT NULL  COMMENT '存活' DEFAULT 1,
    `redirect` VARCHAR(100)   COMMENT '重定向',
    KEY `idx_menu_created_b6922b` (`created_at`),
    KEY `idx_menu_updated_e6b0a1` (`updated_at`),
    KEY `idx_menu_name_b9b853` (`name`),
    KEY `idx_menu_path_bf95b2` (`path`),
    KEY `idx_menu_order_606068` (`order`),
    KEY `idx_menu_parent__bebd15` (`parent_id`)
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS `role` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `created_at` DATETIME(6) NOT NULL  DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL  DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `name` VARCHAR(20) NOT NULL UNIQUE COMMENT '角色名称',
    `desc` VARCHAR(500)   COMMENT '角色描述',
    KEY `idx_role_created_7f5f71` (`created_at`),
    KEY `idx_role_updated_5dd337` (`updated_at`),
    KEY `idx_role_name_e5618b` (`name`)
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS `user` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `created_at` DATETIME(6) NOT NULL  DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL  DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `username` VARCHAR(20) NOT NULL UNIQUE COMMENT '用户名称',
    `user_no` VARCHAR(16)  UNIQUE COMMENT '用户编号',
    `alias` VARCHAR(30)   COMMENT '姓名',
    `email` VARCHAR(255) NOT NULL UNIQUE COMMENT '邮箱',
    `phone` VARCHAR(20)   COMMENT '电话',
    `password` VARCHAR(128)   COMMENT '密码',
    `is_active` BOOL NOT NULL  COMMENT '是否激活' DEFAULT 1,
    `is_superuser` BOOL NOT NULL  COMMENT '是否为超级管理员' DEFAULT 0,
    `last_login` DATETIME(6)   COMMENT '最后登录时间',
    `dept_id` INT   COMMENT '部门ID',
    KEY `idx_user_created_b19d59` (`created_at`),
    KEY `idx_user_updated_dfdb43` (`updated_at`),
    KEY `idx_user_usernam_9987ab` (`username`),
    KEY `idx_user_user_no_4dfb5f` (`user_no`),
    KEY `idx_user_alias_6f9868` (`alias`),
    KEY `idx_user_email_1b4f1c` (`email`),
    KEY `idx_user_phone_4e3ecc` (`phone`),
    KEY `idx_user_is_acti_83722a` (`is_active`),
    KEY `idx_user_is_supe_b8a218` (`is_superuser`),
    KEY `idx_user_last_lo_af118a` (`last_login`),
    KEY `idx_user_dept_id_d4490b` (`dept_id`)
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS `course` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `created_at` DATETIME(6) NOT NULL  DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL  DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `name` VARCHAR(100) NOT NULL  COMMENT '课程名称',
    `description` VARCHAR(500)   COMMENT '课程描述',
    `teacher_id` BIGINT NOT NULL COMMENT '教师ID',
    UNIQUE KEY `uid_course_name_dbcf51` (`name`, `teacher_id`),
    CONSTRAINT `fk_course_user_17082085` FOREIGN KEY (`teacher_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
    KEY `idx_course_created_eae14b` (`created_at`),
    KEY `idx_course_updated_366ffe` (`updated_at`),
    KEY `idx_course_name_3ad36f` (`name`),
    KEY `idx_course_teacher_81a272` (`teacher_id`)
) CHARACTER SET utf8mb4 COMMENT='一门由教师负责的课程。';

CREATE TABLE IF NOT EXISTS `class_session` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `created_at` DATETIME(6) NOT NULL  DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL  DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `start_time` DATETIME(6) NOT NULL  COMMENT '开始时间',
    `end_time` DATETIME(6) NOT NULL  COMMENT '结束时间',
    `classroom` VARCHAR(100)   COMMENT '教室',
    `class_name` VARCHAR(100)   COMMENT '班级',
    `course_id` BIGINT NOT NULL COMMENT '课程ID',
    CONSTRAINT `fk_class_se_course_176e028b` FOREIGN KEY (`course_id`) REFERENCES `course` (`id`) ON DELETE CASCADE,
    KEY `idx_class_sessi_created_38af0a` (`created_at`),
    KEY `idx_class_sessi_updated_8ab12b` (`updated_at`),
    KEY `idx_class_sessi_start_t_dfa305` (`start_time`),
    KEY `idx_class_sessi_end_tim_17f41c` (`end_time`),
    KEY `idx_class_sessi_course__d8f73b` (`course_id`),
    KEY `idx_class_sessi_course__ab0726` (`course_id`, `start_time`)
) CHARACTER SET utf8mb4 COMMENT='课程的一次课堂会话。';

CREATE TABLE IF NOT EXISTS `emoji_record` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `emoji_type` VARCHAR(32) NOT NULL  COMMENT 'Emoji类型',
    `timestamp` DATETIME(6) NOT NULL  COMMENT '记录时间' DEFAULT CURRENT_TIMESTAMP(6),
    `source` VARCHAR(10) NOT NULL  COMMENT '记录来源' DEFAULT 'MANUAL',
    `confidence` DOUBLE   COMMENT 'AI置信度',
    `device_source` VARCHAR(100)   COMMENT '设备来源',
    `session_id` BIGINT NOT NULL COMMENT '课堂会话ID',
    `user_id` BIGINT COMMENT '用户ID',
    CONSTRAINT `fk_emoji_re_class_se_44989c90` FOREIGN KEY (`session_id`) REFERENCES `class_session` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_emoji_re_user_53c5cd97` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE SET NULL,
    KEY `idx_emoji_recor_emoji_t_4f5e53` (`emoji_type`),
    KEY `idx_emoji_recor_timesta_5a5215` (`timestamp`),
    KEY `idx_emoji_recor_source_aa1449` (`source`),
    KEY `idx_emoji_recor_session_024140` (`session_id`),
    KEY `idx_emoji_recor_user_id_8a4fa7` (`user_id`),
    KEY `idx_emoji_recor_session_d3c4fb` (`session_id`, `timestamp`),
    KEY `idx_emoji_recor_user_id_5b865a` (`user_id`, `timestamp`),
    KEY `idx_emoji_recor_source_0d0840` (`source`, `timestamp`)
) CHARACTER SET utf8mb4 COMMENT='学生手动或 AI 生成的一条情绪记录。';

CREATE TABLE IF NOT EXISTS `schedule_user` (
    `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `created_at` DATETIME(6) NOT NULL  DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL  DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `scheduled_at` DATETIME(6) NOT NULL  COMMENT '安排时间' DEFAULT CURRENT_TIMESTAMP(6),
    `session_id` BIGINT NOT NULL COMMENT '课堂会话ID',
    `user_id` BIGINT NOT NULL COMMENT '用户ID',
    UNIQUE KEY `uid_schedule_us_session_3665c2` (`session_id`, `user_id`),
    CONSTRAINT `fk_schedule_class_se_619cccc0` FOREIGN KEY (`session_id`) REFERENCES `class_session` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_schedule_user_29ab731b` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
    KEY `idx_schedule_us_created_4dd762` (`created_at`),
    KEY `idx_schedule_us_updated_1063e6` (`updated_at`),
    KEY `idx_schedule_us_schedul_36d55c` (`scheduled_at`),
    KEY `idx_schedule_us_session_f103ca` (`session_id`),
    KEY `idx_schedule_us_user_id_c4d0fc` (`user_id`)
) CHARACTER SET utf8mb4 COMMENT='课堂会话中的用户排课关系。';

CREATE TABLE IF NOT EXISTS `aerich` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `version` VARCHAR(255) NOT NULL,
    `app` VARCHAR(100) NOT NULL,
    `content` JSON NOT NULL
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS `role_api` (
    `role_id` BIGINT NOT NULL,
    `api_id` BIGINT NOT NULL,
    FOREIGN KEY (`role_id`) REFERENCES `role` (`id`) ON DELETE CASCADE,
    FOREIGN KEY (`api_id`) REFERENCES `api` (`id`) ON DELETE CASCADE,
    UNIQUE KEY `uidx_role_api_role_id_ba4286` (`role_id`, `api_id`)
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS `role_menu` (
    `role_id` BIGINT NOT NULL,
    `menu_id` BIGINT NOT NULL,
    FOREIGN KEY (`role_id`) REFERENCES `role` (`id`) ON DELETE CASCADE,
    FOREIGN KEY (`menu_id`) REFERENCES `menu` (`id`) ON DELETE CASCADE,
    UNIQUE KEY `uidx_role_menu_role_id_90801c` (`role_id`, `menu_id`)
) CHARACTER SET utf8mb4;

CREATE TABLE IF NOT EXISTS `user_role` (
    `user_id` BIGINT NOT NULL,
    `role_id` BIGINT NOT NULL,
    FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
    FOREIGN KEY (`role_id`) REFERENCES `role` (`id`) ON DELETE CASCADE,
    UNIQUE KEY `uidx_user_role_user_id_d0bad3` (`user_id`, `role_id`)
) CHARACTER SET utf8mb4;