# 实际使用的 AI 服务与模型

修订日期：2026-11-13。本文是当前实现说明，不是模型选型计划。

## 1. AI服务究竟是什么

本项目使用**自部署、独立 Python 进程 `emoji_ai.browser_service`**。
没有调用 DeepFace 云服务、FER 云服务、ChatGPT/其他外部大模型 API，也不需要第三方推理 API Key。
“AI服务身份”是本项目后端签发的服务器凭证，不是学生摄像头设备注册或厂商账号。

学生只需支持 `getUserMedia` 的浏览器和普通内置/USB 摄像头：

```text
学生原课堂页 → getUserMedia → 时间槽取样 → 内存JPEG
→ 同源 /ai-stream/frames → 独立Python服务 /frames
→ OpenCV检测/表情分类 → 单人门/阈值/五类映射
→ 本项目独立Bearer凭证 → /api/v1/ai/emoji-results
→ 原EmojiRecord → 原教师看板/管理统计/CSV
```

浏览器短期上传凭证 `bcc_…` 只能代表一次已排课学生的采集授权；
独立服务长期凭证 `aic_…` 只在服务器secret文件中存在。学生JWT不能写AI结果。
服务不直接连接业务数据库。outbox是匿名元数据重试队列，不是第二套课堂数据库。

## 2. 默认和可选模型

| 项目 | 默认 `edge` | 可选 `standard` |
| --- | --- | --- |
| 人脸检测 | OpenCV YuNet 2023mar | DeepFace包装的YuNet 2023mar |
| 表情分类 | OpenCV Zoo `facial_expression_recognition_mobilefacenet_2022july.onnx` FP32 | DeepFace Emotion ONNX |
| 框架 | OpenCV 4.11.0.86 DNN，CPU | DeepFace 0.0.104 + ONNX Runtime 1.31.1，CPU |
| 模型版本标识 | `opencv-zoo-mobilefacenet-2022july-fp32` | `deepface-emotion-0.0.104-onnx` |
| 是否需要DeepFace | 不需要 | 需要，仅`actions=["emotion"]` |
| TensorFlow/PyTorch | 固定锁不安装 | 当前固定ONNX锁不安装 |
| 状态 | browser示例/本机服务/edge Linux镜像默认 | 独立安装可选；固定真模型验证，未宣称标准版全班/网页现场验收 |

MobileFaceNet文件在这里是**表情分类模型**，不提取身份embedding。不能仅凭模型名称把它写成
人脸识别系统。两路线都不运行年龄、性别、种族、身份识别或个人情绪评分。
一个进程只运行一个profile，模型串行使用；不同时启动两种profile抢同一服务身份。

FER只做了依赖/接口选型对照，未安装或实现adapter，不能写成已支持。
指导书§3.2明确允许OpenCV+DeepFace/FER**或轻量模型**，不要求同时安装两者。
默认edge是已有CPU实测与简化运行依赖的工程选择，不代表已证实比standard更准确。

## 3. 权重来源与复现

正式Git只有`ai-service/models/manifest.json`，不包含权重。
OpenCV来源固定commit `48b10fa505aeb51fbd127fc60a5c660040e823b7`；
DeepFace来自`deepface_models-v1.0` release，再用文件长度和SHA-256固定内容。
所有URL见manifest，下载须显式执行`emoji_ai.prepare`，启动前验证长度/哈希。

| 文件 | 字节 | SHA-256 |
| --- | ---: | --- |
| YuNet | 232589 | `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` |
| MobileFaceNet expression | 4791892 | `4f61307602fc089ce20488a31d4e4614e3c9753a7d6c41578c854858b183e1a9` |
| DeepFace Emotion | 5947004 | `2131942f16003c515f6b1fb09827f9eef111048f033bcc477fbb71f0d446f2a9` |

缺模型、哈希不符或错误engine明确失败，不下载临时替代模型、不fallback到假结果。
Windows两profile使用各自含哈希的CPython3.11锁；Linux只提供edge锁/镜像模板，
不以Windows wheel锁冒充Linux验证。模型历史实测见`AI_MODEL_VALIDATION.md`。

## 4. 映射、采样与隐私

- 七类输出happy/sad/angry/surprised/neutral映射为现有
  `HAPPY/SAD/ANGRY/SURPRISED/NEUTRAL`；fear/disgust赢家拒识，不改选其他标签。
- DeepFace百分比分数归一到`[0,1]`，不二次softmax；edge原始logits做稳定softmax。
- 默认表情阈值0.70、检测阈值0.85、最小脸48px。检测返回的全部候选先判断单人，
  不能因为第二张脸小/低分就将多人画面当成单人；漏检的背景脸仍是模型局限。
- 管理员选5/10/15/30秒，默认10；一节45分钟每端时间预算最多270次，
  实际晚加入/后台/掉线/拒识会减少，不要求凑足记录。
- 原图**会经HTTPS上传**以供独立服务推理，但不保存照片、录像或音频。
  浏览器/服务器内存存在短时原帧，结果固定`user_id=null`，无个人AI历史。
- 授权账号只用于排课/配额/单活动会话；停止清owner/token/活动键，短期票据清理。
  结果匿名不等于鉴权系统绝对不可关联，不承诺跨账号摄像头人脸去重。

## 5. 服务资源与错误边界

本机默认Web3100/API9999/AI9998；生产学生访问可信HTTPS网页与同源帧入口，
AI9998仅内部监听。JSON业务API256KiB/10秒有界读取，帧入口256KiB、
JPEG头1280×720解码前检查、读取5秒，模型单线程、队列最多1帧、
HTTP解析连接最多16、admission默认4。这些是资源上限，不是全班容量指标。

拒绝重复SOF/不支持JPEG头并忽略EXIF自动旋转，避免先验尺寸与native解码语义不一致。
网页一请求在途；过载/断网跳过，不缓存补传旧照片。
仅已经生成的严格匿名事件进入60秒outbox，最终入库还检查采集授权有效；
停止后的未入库结果拒绝。单个采集授权403只拒绝该帧；真正长期凭证401/403停止服务。
审计只存操作元数据，错误不回显密码、token、原图或SQL结构。

## 6. 已验证与尚待验证

已验证：两套固定真模型、匿名映射/过滤/HTTP/幂等、三端权限、Windows普通摄像头网页短测。
没有完成：课堂标注准确率/macro-F1、不同人群/低光/遮挡、全班并发容量与端到端SLA、
2小时soak、目标Linux/Compose/可信TLS实跑。
分数高不等于分类正确，面部表情不等于真实内在心理状态；系统不用于评分、缺勤或诊断。

DeepFace库MIT、YuNet MIT、OpenCV Zoo Apache-2.0许可证保留于`third_party`。
具体权重与训练数据使用条件仍需按发布用途核查；库许可证不能自动代替权重授权。
安装/接入见`ai-service/README.md`与`AI_BROWSER_CAPTURE.md`；复审/测试见
`FINAL_REVIEW.md`、`AI_TEST_REPORT.md`。
