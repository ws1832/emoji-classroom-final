# 表情符号课堂情绪检查器：模块认领清单

本项目在 Vue FastAPI Admin 基础上扩展课堂业务；下列已接入模块按成员边界协作。
修改共享认证/领域/统计契约时同步测试与文档，不另建重复门户或数据库。

## 成员 A：后端与数据库

- `app/models/classroom.py`
- `app/schemas/classroom.py`
- `app/schemas/emoji.py`
- `app/controllers/course.py`
- `app/controllers/session.py`
- `app/controllers/emoji.py`
- 负责数据库迁移、课程/课堂/排课/EmojiRecord 模型和数据权限。

## 成员 B：学生与教师客户端

- `web/src/views/` 下新增学生 emoji、个人历史、教师课堂历史页面
- `web/src/api/index.js` 增加课程、会话、emoji、教师查询接口
- 负责学生注册、登录、修改密码、手动发送 emoji 和教师基础统计。

## 成员 C：管理端与统计导出

- `app/services/statistics.py`
- `app/services/export.py`
- `app/api/v1/dashboard/`
- `app/api/v1/statistics/`
- `app/api/v1/courses/`
- `app/api/v1/sessions/`
- 负责管理员课程/课堂/排课、实时看板、多维统计、CSV 导出。

## 成员 D：AI 服务集成

- `app/services/ai_ingest.py`
- `app/api/v1/ai/`
- 新增独立 `ai-service/` 目录，实现视频帧采样、人脸检测、情绪分类、置信度过滤和重试。
- AI 记录必须带 `source=AI`、`confidence`、`session_id`，默认不保存原始图像或视频。

### D 的 2026-11-13 联调范围

- 学生原课堂页嵌入免安装网页摄像头采样；服务器独立模型、短期授权、
  单人门、时槽配额、匿名幂等入库，不建立第二套用户/课堂/记录数据库。
- 管理员全局课堂采集管理，教师只读所授课堂状态；普通 ADMIN 不要求开启超级用户。
- 与 A/C 联调课程和课堂 ADMIN 全局范围，与 B 联调管理员导航/教师详情/学生摄像头生命周期；
  原手动反馈、历史、看板、统计、CSV 契约保留。
- 增量迁移3、部署模板、接口/浏览器/模型回归、正式接入手册及测试报告一并交付。
  私人计划、凭证、模型权重、图片、日志和本地工具不进入 Git。
- 最终复审同步共享安全修复：无正文审计、JWT改密撤销、随机密码重置、ADMIN边界、
  图片解析和服务拒绝隔离、依赖锁补丁与当前AI服务说明；不更改原课堂/MANUAL/统计数据契约。

## 集成约定

1. API 前缀统一为 `/api/v1`，响应沿用现有 `Success/Fail` 格式。
2. 每个模块至少提供一个单元测试和一个接口测试。
3. 所有需要登录的接口使用 `DependAuth`；管理员接口使用 `DependPermission`，业务数据还要做教师/学生归属校验。
4. AI 接口使用独立服务令牌，不接受学生 JWT。
5. 合并前必须补充 OpenAPI 示例、数据库迁移和 README 使用说明。
