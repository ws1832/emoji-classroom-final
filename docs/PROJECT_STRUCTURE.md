# 当前项目结构

修订：2026-11-13。核心业务与网页摄像头已实现，不是TODO骨架。

```text
Vue三端 → 原JWT API → FastAPI Router/Controller/Service → Tortoise → SQLite/MySQL
学生getUserMedia → 内存JPEG → 独立Python AI → 独立凭证/票据API → 同一EmojiRecord
```

- `app/api/v1/base`：注册、登录、userinfo/menu/api、改密；用户JWT沿用token头。
- `users/roles/auditlog`：ADMIN业务角色+动态RBAC，无公开menu/api/dept CRUD入口。
- `courses/sessions/emoji/dashboard/statistics`：原A/B/C领域、归属/排课、统计/CSV。
- `services/ai_jobs.py`：身份/模型快照/租约代际；`browser_capture.py`：短期授权/时槽/清理；`ai_ingest.py`：严格匿名事务/receipt。
- `core`：认证/权限、字节读取边界、无正文审计、异常；`schemas/models`：Pydantic契约和ORM。
- `ai-service/src/emoji_ai`：模型/browser_service/outbox/publisher，旧CLI/file Worker仅回归。
- `web/src/views/student/teacher/classroom/system`：三端；相机嵌原学生课堂，状态管理嵌原看板。
- `migrations/models`：提交0→1→2→3，`scripts/migrate.py`唯一入口，SQL结构参考不能混用。
- `deploy/compose*.yml`：分服务部署模板，非Linux生产验收。
- `tests`、`ai-service/tests`、`web/tests`：业务/安全/模型/显式环境回归。

Dept/DeptClosure、少量schema保留旧库兼容，无产品入口；i18n/主题/图标/表格是通用基础。不为清理无迁移删除模型。`.local/tools`、权重/媒体/数据库/日志/真实secret配置不提交。
