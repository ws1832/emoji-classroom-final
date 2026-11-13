# D：当前 AI 集成与实验要求

修订：2026-11-13。唯一产品入口为原学生课堂的浏览器摄像头，管理员全局配置、教师所授只读、学生本机授权。实际服务/模型见[AI_SERVICE](AI_SERVICE.md)，接入见[AI_BROWSER_CAPTURE](AI_BROWSER_CAPTURE.md)。

## 必做对照

| 要求 | 当前实现 | 验证边界 |
| --- | --- | --- |
| 视频帧采样 | StudentCameraCapture/getUserMedia→JPEG→browser_service | 本机硬件短测，全班待测 |
| 检测/分类 | YuNet+edge MobileFaceNet/可选DeepFace Emotion | 两套真模型，课堂标注待测 |
| 五类映射 | five-emotions-v1，原EmojiType | fear/disgust拒识 |
| 频率/阈值可配 | ADMIN+动态RBAC BrowserPolicy | 5/10/15/30秒默认10，教师学生不可写 |
| 来源/课堂/时间/分数 | 独立身份+job+frame推导 | 不信任学生标签或身份覆盖 |
| 默认匿名/不存图 | user_id=None、内存帧、严格元数据 | DB/outbox/audit不留媒体/embedding |
| 重试/日志 | 60秒匿名outbox/jitter/UUID | 最终授权仍有效，不补旧照片 |
| 独立令牌 | aic服务身份/bcc短期能力/JWT分离 | 一次显示/hash/轮换撤销 |
| 业务耦合 | 同一User/Course/Session/Schedule/EmojiRecord | 原MANUAL/历史/看板/CSV保留 |
| REST/分层/迁移 | Router→Service→ORM，0→1→2→3 | SQLite/MySQL真验证，生产另验收 |

指导书允许OpenCV+DeepFace/FER或轻量模型，不要求同时两库，也不指定公共摄像头/固定次数/教师启停权。管理员统一控制为符合要求的最小权限设计。

## 分层和模型

```text
Vue三端 → 原用户JWT → FastAPI控制面
学生摄像头 → bcc上传 → 独立Python模型
独立aic → frame/lease/receipt → 原EmojiRecord → 原看板/统计/CSV
```

新增AIDevice/Credential/Job/Lease/Receipt/Metadata及BrowserCapture/Frame/Budget，不复制业务库。短期owner用于授权/防重，停止清除；HMAC配额不关联结果、不公开教师。各课堂job/lease独立，同一服务有界接收，不声称无限并行。

## 当前 API（/api/v1前缀）

| 路径 | 身份 | 用途 |
| --- | --- | --- |
| ai/browser/classrooms/{id} GET | 排课STUDENT | 本课堂策略 |
| .../classrooms/{id}/captures POST | 排课STUDENT/consent:true | 单活动会话/内存bcc |
| .../captures/{uuid}/renew/stop POST | 原学生JWT | 20秒续期/停止60秒授权 |
| ai/browser/manage/{id} GET | 所属TEACHER/ADMIN | 匿名状态/服务器can_configure |
| ai/browser/manage/{id} PUT | ADMIN+RBAC | 配置/启停/revision |
| ai/devices/credentials | ADMIN+RBAC | 服务器身份，不是学生设备 |
| ai/worker/heartbeat | 独立aic | 5秒心跳/45秒租约/fencing |
| ai/browser/worker/claim/outcomes | 独立aic | 时槽票据/单人检查 |
| ai/emoji-results及batch | aic+job/lease/frame | 匿名v1元数据，batch最多50 |

JPEG不进业务API：/ai-stream/frames代理独立服务/frames。学生JWT不能写source=AI；旧ai/jobs仅CLI回归，写限ADMIN，无旧公共相机UI。
事件字段contract_version/event_id/job_id/generation/lease_id/captured_at/emoji_type/confidence/model_version/config_revision/mapping_version/quality；严格正整数/UUIDv4/finite[0,1]/快照一致，禁止raw/坐标/身份/session覆盖。UTC RFC3339入旧表转北京wall-clock。

## 安全生命周期

同账号课堂单会话，server时槽重开不重置，UUID/payload幂等冲突拒绝。无脸/多人/低分不写，AI不计唯一学生人数。停止/改密/后台/登出/到期释放track，入库时仍最终检查授权。
JWT要求exp/严格ID/credential_tag，改密撤销旧JWT及采集能力，无新增业务表；本轮升级旧JWT需重登。审计只操作元数据、错误不反射密码/token/SQL。
JSON256KiB/10秒；图像256KiB/1280×720/5秒；模型串行/队列1/admission4/HTTP16，均资源上限非容量证明。元数据TTL60秒，停止未入库拒绝；旧file Worker15分钟只历史规则。
原分页/statistics数组/dashboard累计/CSV列BOM及注入防护保留。部署/验收见AI_OPERATIONS/AI_TEST_REPORT，修复见FINAL_REVIEW。
