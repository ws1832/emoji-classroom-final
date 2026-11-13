# 当前运行与交接手册

修订：2026-11-13。学生网页唯一产品采集入口，独立服务只推理，不打开服务器摄像头。首次接入及三端操作统一见[AI_BROWSER_CAPTURE](AI_BROWSER_CAPTURE.md)§8–9，模型见[AI_SERVICE](AI_SERVICE.md)，安装见ai-service/README。

## 操作与故障

原API/Web→提交迁移→管理员注册服务器身份/保存一次凭证/配置AI_BROWSER_DEVICE_ID→准备hash权重/启动browser_service→管理员开启当前课堂→学生网页授权普通相机→教师只读匿名状态。停止/结束/登出/后台/改密清track/授权，MANUAL继续可用。

| 状态 | 处理 |
| --- | --- |
| service_ready=false/503 | 查doctor/凭证/来源/心跳 |
| degraded/heartbeat_unavailable | 后端断线或旧45秒租约，不绕fencing |
| no_face/multi_face/filtered | 单人/质量未过，不补NEUTRAL |
| 429/busy | 跳过槽，验容量/间隔，不缓存补图 |
| 401/410 | 授权到期撤销，停止后明确重开；长期凭证需管理员轮换 |
| model_failed | 缺模型/hash/engine/推理错，明确失败无fake |

模型串行/队列1/admission4/HTTP16，图片256KiB/1280×720；心跳5秒/lease45秒，capture60秒/20秒续期，outbox60秒且最终授权有效才入库。单帧跨范围403不关闭共享服务，长期认证失败停止。
审计只操作元数据，无图片/密码/token/SQL异常；修复不清历史备份中的旧敏感日志，维护者按保留政策受限处理。

## 生产模板（仍需目标实跑）

仅deploy/compose.yml和compose.browser.yml，旧根Dockerfile/entrypoint已删除。默认Web127.0.0.1:8080，DB/AI不公开端口；API普通MySQL用户，root secret不入API，模型/配置/secret只读、outbox可写。
受限.local/deploy存不同mysql_password/mysql_root/jwt_key/admin_password；DEBUG=false、随机SECRET_KEY≥32、强初始密码、明确CORS_ORIGINS。外层可信TLS网页+同源帧入口，关闭图片录制/缓存/trace。

```sh
docker compose -f deploy/compose.yml up -d --build
# 注册身份、准备模型/browser.json/ai_service_token及AI_BROWSER_DEVICE_ID后：
docker compose -f deploy/compose.yml -f deploy/compose.browser.yml up -d --build
```

复制browser.linux.example.json修改实际HTTPS后端/网页来源；学生localhost不是服务器。AI容器不映USB。Linux仅edge模板，standard未锁/实跑。网关有body/时间/连接限制；登录注册每IP5次/分钟burst10，429，校园共用出口应实测调参；并非已实现分布式账号限流，不公开裸API/Vite绕过网关。

## 升级/备份/恢复

scripts/migrate.py唯一提交迁移0→1→2→3入口；不生成/删除迁移，生产单次/API副本AUTO_INIT_DB=false。历史手写mysql_schema先字段diff，勿混bootstrap/ALTER。本轮JWT修订无新增表，旧JWT重新登录，改密/reset清相机授权，直接Argon2库兼容旧哈希、不重置已有密码。

```powershell
.\.venv\Scripts\python.exe scripts/backup_sqlite.py --source db.sqlite3 --destination .local/backups/pre-upgrade.sqlite3
.\.venv\Scripts\python.exe scripts/migrate.py
```

活跃SQLite WAL用online backup，拒绝覆盖/check integrity；停服新路径SQLITE_PATH验证行数/FK/迁移/权限再切换，不在线搬库/WAL。MySQL受限client文件：

```sh
mysqldump --defaults-extra-file=/secure/mysql-client.cnf --single-transaction --routines --triggers emoji_classroom > /secure/backups/pre-upgrade.sql
mysql --defaults-extra-file=/secure/mysql-client.cnf emoji_classroom_restore < /secure/backups/pre-upgrade.sql
```

新库恢复检查MANUAL/匿名AI/receipt/排课；MySQL DDL可能隐式提交，回滚优先备份。
业务不自动删除，receipt脚本默认30天/最多500，先dry-run：

```sh
python scripts/cleanup_ai_receipts.py --days 30
python scripts/cleanup_ai_receipts.py --days 30 --apply
```

短期Capture/Frame/Budget心跳清理；服务停机授权失效，恢复清残留，不承诺到期瞬间物理删除。secret/备份不进Git。

## 历史回归与发布门

emoji_ai.worker/file/usb/rtsp仅历史回归，不保留公共相机产品方案；CLI示例测试验证HTTP/幂等/故障，不展示旧UI，管理写限ADMIN；不同身份不抢网页incarnation，旧outbox15分钟不套网页。
仍须标注macro-F1/拒识、人群光线、50端容量/过载/SLA、2小时soak、Linux/Compose/TLS现场实跑。单图/35秒只是链路证据。CSV原maxID/500行keyset/100000上限、列BOM防注入，AI不是学生人数。详见AI_TEST_REPORT/FINAL_REVIEW。
