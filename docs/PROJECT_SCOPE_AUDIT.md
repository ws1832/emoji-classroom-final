# 项目范围与清理结论

修订：2026-11-13，依据根实验指导书。

必做学生MANUAL/历史、教师所授历史/统计、管理员全局用户/排课/统计/CSV/看板，以及独立AI采样/检测/五类映射/阈值/同库匿名结果均已有实现。指导书不要求公共摄像头或固定次数；产品仅学生网页普通摄像头。

保留JWT/Argon2/RBAC、动态Menu/Api、审计操作元数据、领域查询、通用前端基础和第三方许可证。Dept/DeptClosure仅旧库兼容，无产品入口，不无迁移删除。旧CLI/file Worker仅真实HTTP/故障恢复回归，不展示公共摄像头UI。

本轮删除模板演示站/截图、无引用旧AIJobPanel、根旧单容器Dockerfile及nginx/entrypoint、Makefile删除数据库/迁移的clean-db目标。统一分服务Compose和提交迁移入口，原MIT版权/模型许可证保留。

Tortoise+Aerich0→1→2→3支持SQLite/MySQL。mysql_schema.sql是历史手写参考，其余bootstrap/AI SQL也不替代迁移历史；新旧库均scripts/migrate.py，不混多条初始化路线。

仍需课堂标注质量、容量/长测、Linux/Compose/TLS现场验收；不把历史测试数字当发布门通过。当前状态见AI_TEST_REPORT/FINAL_REVIEW。
