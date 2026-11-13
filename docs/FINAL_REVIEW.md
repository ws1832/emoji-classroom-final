# 最终代码、安全与文档复审

日期：2026-11-13。范围：D 与其调用的原认证、权限、课堂/统计接口、三端页面、
独立推理服务、依赖锁、部署模板和正式文档。复审基线为 `cecd5b1`；
私人假设清单、计划、原始扫描报告、凭证和运行文件留在本地忽略目录，不随本报告提交。

## 1. 与实验要求及既有模块的匹配

依据根《表情符号课堂情绪检查器系统》实验指导书：

| 要求 | 当前实现 |
| --- | --- |
| §2.1–2.2 三端职责与管理端功能 | 学生原手动反馈/个人历史保留；教师所授课堂只读；管理员全局用户/排课/统计/CSV，没有“我的课堂” |
| §3.1 AI独立部署 | 学生网页采样，独立Python服务推理，REST提交原后端；不另建业务数据库 |
| §3.2 OpenCV+DeepFace/FER或轻量模型 | 默认edge轻量ONNX，可选standard DeepFace Emotion，FER未集成 |
| §4/§5 密码、RBAC、CSV、独立AI令牌 | 加盐Argon2、JWT和动态RBAC加业务归属、CSV防注入、服务器Bearer与用户token分离 |
| §6 五类/频率/阈值/匿名/重试/局限 | 五类映射，默认10秒可配置，阈值过滤，AI的user_id为空，原图不落盘，有界元数据重试及误判说明 |
| §9 测试与运行证据 | 原A/B/C、接口/权限/浏览器、固定真模型、SQLite/MySQL迁移恢复有回归证据；目标环境和容量待验收 |

指导书没有要求公共摄像头、学生必须开相机、固定采样次数，也未指定教师必须控制AI启停。
因此产品仅保留学生网页摄像头：管理员配策略/启停，教师只读，
学生仅授权/释放本机设备。浏览器权限不能由管理员代替。
默认10秒时45分钟时间预算最多270次/端，不要求凑足有效记录。

## 2. 发现及已实施的修复

| 问题/影响 | 实施 | 证据 |
| --- | --- | --- |
| 审计解析完整请求/响应可能保存密码，且鉴权前读取无界正文 | 审计仅操作元数据，不读body/form/CSV；业务写操作先有界读取 | `test_security.py`、`test_d_ai_api.py` |
| 校验/ORM/JWT异常可能反射输入或SQL | 统一受控错误，不返回input/repr/SQL；真实409与HTTP headers保留 | 安全负例、原业务回归 |
| no-store传参被误当JSON字段 | 响应类显式接收HTTP headers；一次性秘密响应真正no-store | API断言及Chromium响应检查 |
| 固定重置密码、创建弱密码、改密旧JWT持续有效 | 随机一次性reset、强密码策略、Argon2旧哈希兼容；JWT含密码状态HMAC；改密撤销相机授权 | `test_security.py`、`test_d_browser_capture.py`、Chromium |
| 畸形JWT类型/非ASCII标记进入异常兜底 | 严格ID/标记格式、固定算法/必需claims，解码非法类型受控401 | JWT边界用例 |
| 动态API误授权可能越过用户/角色/审计业务边界 | ADMIN依赖；普通ADMIN保护超级用户；拒绝自禁用/自删除 | ADMIN负例、原角色/RBAC回归 |
| 已有菜单阻止系统菜单初始化 | 幂等补齐核心菜单，保留自定义名称/项 | 部分菜单专项及真实用户管理页 |
| JPEG多帧头或EXIF解码语义不一致 | 拒绝重复SOF/不支持头；忽略自动旋转，并验证解码尺寸 | `ai-service/tests/test_browser_service.py` |
| 单采集会话403导致共享AI线程退出 | claim/outcomes403仅拒该帧；长期认证失败仍停止 | 独立服务HTTP负例 |
| 旧依赖存在已知公告、升级可能破坏RBAC路由扫描 | 兼容升级并固定requirements/uv/pnpm/platform锁，保留APIRoute扫描 | 全量回归、pip check、frozen lock、公告扫描 |
| 开发/网关边界过宽 | 默认明确CORS且无credentials；生产拒绝通配来源/弱初始密码；run.py和Vite只监听本机；Nginx超时/连接/认证限流模板 | 设置测试；网关尚未真实运行 |
| 前端秘密或状态残留 | 随机密码关闭/卸载清除、不存storage；创建弹窗清密码；改密logout；修正禁用loading和角色字段校验 | Chromium、auth回归、构建 |

认证撤销不更改原EmojiRecord、课堂或手动历史契约；本轮无新增迁移。
升级前JWT需要重新登录。未自动删除旧审计/备份，避免擅自修改历史；
旧敏感日志应由维护者按保留政策受限处置。

## 3. 实际AI服务说明

详见 [AI_SERVICE](AI_SERVICE.md)，该文是当前实现事实，不是选型计划：

- 自部署 `emoji_ai.browser_service`，无外部LLM/云推理API，不需要厂商API Key。
- **默认edge**：OpenCV4.11.0.86 YuNet + OpenCV Zoo MobileFaceNet表情分类FP32 ONNX，
  CPU DNN。模型不是身份embedding，不运行身份/年龄/性别等任务。
- **可选standard**：DeepFace0.0.104，`actions=["emotion"]`，
  YuNet与ONNX Runtime1.31.1 CPU；固定真实模型验证，不冒充全班网页现场验收。
- **FER未集成**，只做过依赖/接口对照。实验允许轻量模型，并非必须同时装DeepFace/FER。
- 模型manifest固定来源、字节数、SHA-256；缺失/不符明确失败，不临时下载替代模型或假结果。
- 学生帧会上传至服务器内存，结果匿名不等于原图不传输或鉴权系统完全不可关联。
  无脸/多人/低分与不支持的赢家类别拒识，原图/录像/音频不存储。
- 串行模型、队列1、admission4、HTTP连接16、256KiB/1280×720是资源边界，
  不代表已验证全班容量。仅严格匿名元数据进入60秒outbox，停止后未入库事件拒绝。

## 4. 清理与保留理由

删除无引用的旧公共采集 `AIJobPanel.vue`、原模板 `deploy/sample-picture` 素材、
旧根单容器Dockerfile/entrypoint/web.conf，以及Makefile删除数据库/迁移的clean-db。
删除将HTML错误标为Python的旧GitHub语言统计属性，不伪装源码语言。
移除README模板演示站/截图说明，统一现有分服务Compose、单迁移入口、
学生网页接入和当前模型；共享Layout统一导入，消除重复静态/动态导入提示。

保留：

- 原用户/课程/课堂/排课/EmojiRecord、动态菜单/Api、通用页面和基础组件，
  不为精简破坏A/B/C。
- `Dept/DeptClosure`旧库兼容模型：无产品入口，不无迁移删除。
- 旧CLI/file Worker与对应测试：仅HTTP/故障恢复回归，不作为公共相机产品方案。
- `database`历史参考SQL：明确不能代替Aerich0→1→2→3，
  不并行混用bootstrap/手工ALTER/迁移。
- 原MIT版权和模型第三方许可证，不能把来源归属当冗余删掉。

正式提交包含源码、测试、文档、锁和有理由的删除。
`.local`、`tools`、配置/secret、权重、DB/WAL、媒体、截图/trace、
备份和日志全部排除；私人规划不会被Git记录。

## 5. 回归证据

最新执行结果见 [AI_TEST_REPORT](AI_TEST_REPORT.md)§7：

- 后端完整 **127 passed / 2 skipped**，两个MySQL专项另跑 **2 passed**；
  总129项有通过证据，不与历史/重复执行计数相加。
- 独立AI **49 passed / 0 skipped**，显式两套固定真模型。
- 前端 **57 + 5 + 3 passed**，Vite生产构建通过。
- backend/AI `pip check`、`uv lock --check`、前端frozen lock一致。
- pip-audit/pnpm audit查询时业务/前端/三种AI锁的已知公告为0，
  原始JSON留本地。扫描只覆盖包公告，不证明native解码器/镜像OS或未知问题全部安全。
- 新代码API/Web/AI健康检查ready；实际学生页面模拟流3次no_face、
  不入库、停止释放、存储无秘密。此前真实硬件2accepted/1no_face单独保留，未重复计验收。

## 6. 未完成的正式运行验收

1. 获准课堂标注集的macro-F1、混淆矩阵、拒识、人群/低光/遮挡/真实多人测试。
2. 目标班级规模、跨课堂并发、5/10/15/30秒负载、过载恢复、端到端SLA。
3. 完整2小时soak、真实网络故障、正式MySQL切换/RTO演练。
4. 目标Linux/Compose构建与运行、可信TLS、真实Nginx限流及校园共享出口调参。
5. 账号级/多副本认证限流目前未实现；网关每IP限制不能当作分布式防爆破。
   公开学生/教师注册是原实验能力，不自动排课/授ADMIN；生产可另加邀请/身份审核流程。
6. 容器基础镜像/操作系统公告和权重/训练数据发布条件仍需目标发布审查。
   JPEG格式门不是native内存安全证明，不能据此宣称所有安全问题消除。

软件功能与本轮修复有证据；仍需上述环境和数据条件才能作“正式课堂生产验收通过”结论。
