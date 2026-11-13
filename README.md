# 表情符号课堂情绪检查器

基于 Vue 3 + Naive UI + FastAPI + Tortoise ORM，学生、教师、管理员及独立 AI 服务共用原用户、课程、课堂、排课和 EmojiRecord。项目从 Vue FastAPI Admin 扩展，保留原 MIT 版权，不将模板演示站或截图当作本项目成果。

## 三端职责

| 身份 | 功能 |
| --- | --- |
| 学生 | 注册/登录/改密、已排课堂手动 emoji、个人手动历史、网页摄像头匿名采样 |
| 教师 | 所授课堂历史、统计、看板；只读匿名采集状态 |
| 管理员 | 全局用户/角色/课程/课堂/排课、看板/统计/CSV、课堂采集策略和 AI 服务身份 |

管理员没有“我的课堂/我的教室”；教师不配置 AI 或启停课堂采集；学生只授权/停止自己的本机摄像头。指导书没有要求公共摄像头、固定次数或强制学生开启相机，原手动反馈始终保留。

## 实际使用的 AI

**自部署的独立 Python 服务 `emoji_ai.browser_service`，不是外部大模型/云 API。** 学生普通内置/USB 摄像头通过浏览器 `getUserMedia` 采样，无需安装 Python、模型或插件。网页发送内存 JPEG 单帧，由独立服务推理，再凭服务器身份写入原 API/同一业务库。

| profile | 模型/框架 | 状态 |
| --- | --- | --- |
| **edge（默认）** | OpenCV 4.11.0.86 YuNet + OpenCV Zoo MobileFaceNet **表情分类** FP32 ONNX，CPU DNN | 固定真模型/网页硬件短测通过 |
| standard（可选） | DeepFace 0.0.104，仅 Emotion + YuNet，ONNX Runtime 1.31.1 CPU | 固定真模型/文件流程验证，非默认 |
| FER | 仅选型对照，未安装/集成 | 不声称支持 |

默认10秒，管理员可选5/10/15/30秒；无脸/多人/低分不入库，fear/disgust赢家拒识。业务AI固定 `user_id=null`，不存原图/视频/音频，不识别身份；模型分数不是心理状态概率，AI观测条数不是学生人数。详见 [AI服务说明](docs/AI_SERVICE.md)。

## Windows 本地启动

需要 Python3.11、Node.js **>=22**、pnpm9、Git。从仓库根执行：

```powershell
git clone -b feature/module_d https://github.com/kasnria001/emoji-classroom-final.git
cd emoji-classroom-final
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

编辑 `.env`：无MySQL时设 `DB_ENGINE=sqlite`，生成随机SECRET_KEY写入该文件；已有配置不要覆盖，已有库先备份。

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
.\.venv\Scripts\python.exe run.py
```

另一个终端：

```powershell
cd web
npm install --global pnpm@9.15.9
pnpm install --frozen-lockfile
pnpm dev
```

Web `http://localhost:3100`；API/Swagger `http://localhost:9999/docs`；健康检查 `/healthz`。开发只本机使用；生产使用dist、反向代理和可信HTTPS，不公开Vite。

空开发库初始化 `admin / 123456`，已有库不重置。生产 `DEBUG=false` 拒绝默认密钥/初始密码，需强BOOTSTRAP_ADMIN_PASSWORD、随机SECRET_KEY和明确CORS_ORIGINS。**修改密码撤销旧JWT和摄像头授权，退出并重新登录；升级本轮代码后旧JWT同样需重新登录。** 管理员reset随机密码只显示一次，不再固定123456。

学生/教师可公开注册，注册不自动排课；管理员由现有管理员创建并授ADMIN，不公开自助提升权限。

## 摄像头与部署

管理员安装独立模型环境、显式准备权重、注册服务器身份、配置AI_BROWSER_DEVICE_ID并启动服务；学生只访问网页授权摄像头，教师不能查看画面。完整步骤见 [接入手册](docs/AI_BROWSER_CAPTURE.md)。开发AI9998，网页同源 `/ai-stream/frames`；长期凭证不进入前端。未配置AI时原MANUAL/历史/统计/CSV仍可用。

正式部署模板为 `deploy/compose.yml` + `deploy/compose.browser.yml`；已删除旧根Dockerfile/entrypoint。Linux/Compose/可信TLS仍需目标环境实跑，不能以模板宣称验收。

## 数据库与测试

唯一受测迁移入口 `scripts/migrate.py`，应用提交Aerich **0→1→2→3**，支持SQLite/MySQL。开发自动应用提交迁移、不生成文件；生产单次迁移，API副本AUTO_INIT_DB=false。不要混跑参考SQL和Aerich，不删除迁移目录处理错误。`mysql_schema.sql`是早期手写参考，不是升级入口。

```powershell
.\.venv\Scripts\python.exe scripts/backup_sqlite.py --source db.sqlite3 --destination .local/backups/pre-upgrade.sqlite3
.\.venv\Scripts\python.exe scripts/migrate.py
.\.venv\Scripts\python.exe -m pytest -q tests
pnpm --dir web run test:auth
pnpm --dir web run test:camera
node --test web/tests/session-date.test.mjs
pnpm --dir web build
```

SQLite活跃WAL用online backup，不裸复制；MySQL用受限客户端文件dump/restore。用户JWT沿用token头，独立AI仅接受服务Bearer，响应沿用 `{code,msg,data}`、OpenAPI `/openapi.json`。真实Worker/Chromium/MySQL需显式环境，不把skip当通过。

## 文档

- [AI服务与模型](docs/AI_SERVICE.md)、[摄像头接入](docs/AI_BROWSER_CAPTURE.md)
- [集成契约](docs/AI_INTEGRATION.md)、[运行手册](docs/AI_OPERATIONS.md)
- [测试证据](docs/AI_TEST_REPORT.md)、[最终复审](docs/FINAL_REVIEW.md)
- [结构](docs/PROJECT_STRUCTURE.md)、[范围](docs/PROJECT_SCOPE_AUDIT.md)、[分工](docs/TEAM_MODULES.md)

`app`后端、`web`三端、`ai-service`独立推理、`migrations`提交迁移、`tests`回归、`deploy`部署模板。`.local`私人计划/凭证/备份/原始报告、`tools`本机工具、权重/媒体/DB/日志/真实配置不进Git；正式源码、测试、文档、锁文件提交。保留许可证和必要基础组件。

本机短测不等于课堂准确率、全班容量、2小时稳定性或Linux生产验收，剩余验证明确见测试报告。
