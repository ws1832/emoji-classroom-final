# 表情符号课堂情绪检查器系统

学生在课堂中主动选择表情符号记录情绪；独立 AI 服务对摄像头视频帧进行实时情绪分析并**匿名**入库；教师查看所授课堂的历史与统计；管理员管理用户、为特定时间安排用户列表、统计并导出数据。

技术栈：Vue 3 + Naive UI + FastAPI + Tortoise ORM + OpenCV（YuNet + MobileFaceNet）。学生、教师、管理员与独立 AI 服务共用同一套用户、课程、课堂、排课与 `EmojiRecord` 数据模型。

## 系统架构

```text
浏览器学生端 (Vue)  ──┐
浏览器管理端 (Vue)  ──┼── REST/JSON ──> 后端 (FastAPI)
                       │                Controller → Service → Model (Tortoise ORM)
独立 AI 服务 (Python) ─┘                      │
                                              ▼
                                        SQLite / MySQL
```

- 后端：FastAPI 分层架构，`app/controllers` 接收请求、`app/services` 实现业务、`app/models` 访问数据库。
- 学生端 / 管理端：Vue 3 单页应用，通过统一 REST API 与后端交互。
- AI 服务：独立 Python 进程，只接收浏览器上传的内存 JPEG 单帧做推理，凭**独立设备凭证**调用后端入库，不直接访问数据库。

## 三端职责

| 身份 | 功能 |
| --- | --- |
| 学生 | 注册 / 登录 / 改密、已排课堂手动 emoji、个人手动历史、网页摄像头匿名采样 |
| 教师 | 所授课堂 emoji 历史与统计、实时看板；只读匿名采集状态 |
| 管理员 | 全局用户 / 角色 / 课程 / 课堂 / 排课、看板 / 统计 / CSV 导出、课堂采集策略与 AI 服务身份管理 |

权限边界在后端强制校验：管理员没有“我的课堂/我的教室”入口；教师不能配置 AI 或启停课堂采集；学生只授权或停止自己的本机摄像头。手动 emoji 反馈始终保留，不强制学生开启摄像头。

## AI 推理服务

**自部署的独立 Python 服务 `emoji_ai.browser_service`，不是外部大模型或云 API。** 学生使用普通内置 / USB 摄像头，通过浏览器 `getUserMedia` 采样，无需安装 Python、模型或插件。网页发送内存 JPEG 单帧，由独立服务推理，再凭服务器身份写入原 API / 同一业务库。

| profile | 模型 / 框架 | 状态 |
| --- | --- | --- |
| **edge（默认）** | OpenCV 4.11 YuNet 人脸检测 + OpenCV Zoo MobileFaceNet 表情分类（FP32 ONNX，CPU） | 已固定真模型，本机真实摄像头短测通过 |
| standard（可选） | DeepFace 0.0.104（仅 Emotion + YuNet），ONNX Runtime 1.31.1 CPU | 已固定真模型，文件流程验证，非默认 |
| FER | 仅选型对照 | 未安装 / 集成，不声称支持 |

处理链路：

```text
摄像头视频 → 浏览器定时抓单帧 JPEG → 人脸检测 → 单人检查
  → 表情分类 → 置信度过滤 → 五类映射 → 匿名事件 → 后端入库
```

- 默认采样间隔 10 秒，管理员可选 5 / 10 / 15 / 30 秒；
- 无脸（`no_face`）、多人（`multi_face`）、低分（`filtered`）不入库；fear/disgust 赢家直接拒识，不强行写成 NEUTRAL；
- AI 业务记录固定 `user_id=None`，不存原图 / 视频 / 音频，不识别身份；
- 模型分数不是心理状态概率，AI 观测条数不等于学生人数。

## 快速开始（Windows 本地开发）

前置要求：Python 3.11、Node.js >= 22、pnpm 9。以下命令均在**项目根目录**执行。

### 1. 后端

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

编辑 `.env`：无 MySQL 时设 `DB_ENGINE=sqlite`；生产环境设置随机 `SECRET_KEY` 与强 `BOOTSTRAP_ADMIN_PASSWORD`。

```powershell
.\.venv\Scripts\python.exe run.py
```

- API / Swagger：`http://127.0.0.1:9999/docs`
- 健康检查：`http://127.0.0.1:9999/healthz`

### 2. 前端

```powershell
cd web
pnpm install --frozen-lockfile
pnpm dev
```

Web 地址：`http://127.0.0.1:3100`。

> 若 PowerShell 禁止运行 `pnpm.ps1`，可改用 `node .\node_modules\vite\bin\vite.js` 直接启动开发服务器。

### 3. AI 服务（需要 AI 功能时）

```powershell
py -3.11 -m venv ai-service\.venv
.\ai-service\.venv\Scripts\python.exe -m pip install --require-hashes -r ai-service\requirements\edge-windows-py311.lock
.\ai-service\.venv\Scripts\python.exe -m pip install setuptools==84.2.1 wheel
.\ai-service\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e ai-service
```

准备模型并启动：

```powershell
.\ai-service\.venv\Scripts\python.exe -m emoji_ai.prepare --profile edge --manifest ai-service\models\manifest.json --model-dir ai-service\models
.\ai-service\.venv\Scripts\python.exe -m emoji_ai.browser_service --config .local\browser-ai\config.json
```

AI 健康检查：`http://127.0.0.1:9998/healthz`（返回 `ready:true`）。

> 完整接入需注册服务身份、签发凭证并配置 `AI_BROWSER_DEVICE_ID`。

### 4. 演示数据与默认账号

空数据库初始化后管理员为 `admin / 123456`。导入演示数据（教师、学生、课程、课堂、排课与 emoji 记录）：

```powershell
.\.venv\Scripts\python.exe scripts\seed_demo.py
```

生成账号：`teacher / Teacher123`、`student / Student123`、`student2 / Student123`。

学生 / 教师可公开注册，注册不自动排课；管理员由现有管理员创建并授予 ADMIN 角色，不公开自助提升权限。

## 摄像头接入要点

- 摄像头是**学生当前电脑**的内置 / USB 摄像头，由浏览器 `getUserMedia` 调用；AI 服务不打开摄像头。
- 学生登录后进入「我的课堂」→ 选择已排课课堂 → 点击「开启摄像头」授权即可，页面显示采样状态、尝试次数与确认入库数。
- 停止摄像头、退出课堂、页面进入后台或授权到期都会释放摄像头 track 并停止新入库。
- 浏览器帧上传走同源 `/ai-stream/frames`，开发环境由 Vite 代理到 AI 服务；生产环境需可信 HTTPS 与关闭请求体录制的反向代理。

## 数据库与迁移

- 唯一受测迁移入口：`scripts/migrate.py`（Aerich 0→1→2→3，支持 SQLite / MySQL）。
- 开发环境自动应用已提交迁移；生产环境单次迁移，API 副本设置 `AUTO_INIT_DB=false`。
- 升级前先备份：

```powershell
.\.venv\Scripts\python.exe scripts/backup_sqlite.py --source db.sqlite3 --destination .local\backups\pre-upgrade.sqlite3
.\.venv\Scripts\python.exe scripts\migrate.py
```

- `database/mysql_schema.sql` 是早期手写参考，不是升级入口；不要混跑参考 SQL 与 Aerich 迁移。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests
.\ai-service\.venv\Scripts\python.exe -m pytest -q -c ai-service\pyproject.toml ai-service\tests
pnpm --dir web run test:auth
pnpm --dir web run test:camera
node --test web\tests\session-date.test.mjs
pnpm --dir web build
```

后端覆盖认证、emoji 流程、课程 / 课堂 / 排课、AI 契约、浏览器采集、容量、MySQL 兼容与安全等；AI 服务覆盖适配器、映射、浏览器服务、outbox、worker 与真实模型冒烟。真实 Worker / Chromium / MySQL 需要显式环境，不把 skip 当作通过。

## 部署

正式部署模板：`deploy/compose.yml` + `deploy/compose.browser.yml`。生产环境使用构建产物 `dist` + 反向代理 + 可信 HTTPS，不公开 Vite 开发服务器。Linux / Compose / TLS 需在目标环境实跑验收。

## 项目结构

```text
app/          后端（controllers / services / models / schemas / settings）
web/          学生端 + 管理端（Vue 3）
ai-service/   独立推理服务（OpenCV / DeepFace 适配器、browser_service、outbox）
migrations/   已提交的 Aerich 迁移
database/     数据库脚本（MySQL / SQLite 参考与升级 SQL）
tests/        后端回归测试
deploy/       Docker Compose 与 Nginx 部署模板
docs/         项目文档
scripts/      备份、迁移、演示数据脚本
```

`.local/`（私人凭证、备份、本地配置）、模型权重、媒体文件、数据库、日志与真实运行配置不进入 Git；正式源码、测试、文档与锁文件提交。

## 验收边界声明

本机单人短测通过不等于课堂准确率、全班吞吐、长时间稳定性或 Linux 生产部署验收；模型未在课堂标注数据上校准，AI 观测条数是时间序列采样而非学生人数。剩余验证项与 AI 局限性分析见实验报告。
