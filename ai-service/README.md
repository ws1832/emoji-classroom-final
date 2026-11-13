# 独立课堂 AI 服务

模型准备、doctor、离线 benchmark、独立 Worker、设备认证、outbox和真实API入库已实现；
文件视频闭环及本机USB短测通过。

**2026-11-13方案更新：产品仅学生网页采集，AI结果强制匿名。**
学生侧不安装本包，管理员在服务器安装模型环境；
浏览器帧入口、短期采集会话与原学生页面已实现并通过本机真实getUserMedia短测。
新版接入/采样规范见 `../docs/AI_BROWSER_CAPTURE.md`。
以下安装与模型检查用于独立AI主机；旧CLI Worker仅作回归工具，不再作为公共摄像头产品入口。

## 1. 验证环境与依赖隔离

已验证 Windows x86_64、CPython 3.11.15、CPU：

- standard：DeepFace 0.0.104 Emotion-only + YuNet，显式 ONNX Runtime 1.31.1 CPU，不安装 TensorFlow/PyTorch。
- edge：OpenCV 4.11.0.86 YuNet + MobileFaceNet 表情 FP32 ONNX（不是身份 embedding 模型），不需要 DeepFace。
- NumPy 2.2.6。FER 暂仅依赖/接口对照，不是已验证生产 profile。
- `requirements/*-windows-py311.lock` 是含 SHA-256 的**此平台 wheel 锁**（含修复版pytest），不宣称覆盖 Linux/macOS。Linux edge锁/容器待验收。
- 实际默认edge、可选standard、自部署而非外部云API的完整说明见 `../docs/AI_SERVICE.md`。

仓库根目录执行：

```powershell
py -3.11 -m venv ai-service/.venv
# 选一种 profile；不要安装到后端 .venv。
.\ai-service\.venv\Scripts\python.exe -m pip install --require-hashes -r ai-service/requirements/standard-windows-py311.lock
# edge 仅替换上面的锁文件：
# .\ai-service\.venv\Scripts\python.exe -m pip install --require-hashes -r ai-service/requirements/edge-windows-py311.lock
.\ai-service\.venv\Scripts\python.exe -m pip install setuptools==84.2.1 wheel
.\ai-service\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e ai-service
.\ai-service\.venv\Scripts\python.exe -m pip check
```

也可用于开发快速安装 `pip install -e "./ai-service[standard,test]"`，但正式复现使用平台锁。后端 `requirements.txt` 没有新增推理依赖。

## 2. 显式准备模型与离线检查

权重不进 Git，只有不可变来源/版本/长度/SHA-256 清单 `models/manifest.json` 提交。OpenCV 文件 URL 固定 Git commit，DeepFace release 文件额外以 SHA-256 固定内容。下载过程有限长度、哈希校验、原子替换，不把错误页当模型。

```powershell
.\ai-service\.venv\Scripts\python.exe -m emoji_ai.prepare --profile standard --manifest ai-service/models/manifest.json --model-dir ai-service/models
.\ai-service\.venv\Scripts\python.exe -m emoji_ai.prepare --profile edge --manifest ai-service/models/manifest.json --model-dir ai-service/models
.\ai-service\.venv\Scripts\python.exe -m emoji_ai.cli doctor --profile standard --manifest ai-service/models/manifest.json --model-dir ai-service/models
.\ai-service\.venv\Scripts\python.exe -m emoji_ai.cli doctor --profile edge --manifest ai-service/models/manifest.json --model-dir ai-service/models
```

离线启动前验证文件，缺失/哈希不符明确失败，不静默换模型或切到 fake。一个进程使用一个 profile/检测配置，DeepFace global engine/model cache 不宜跨任务修改。浏览器多输入推理的并发/线程预算须独立实测。

## 3. Benchmark 与测试

自备已获准本地图片，不将素材或个人路径提交 Git。脚本仅读取图片、输出匿名汇总，不输出图片、坐标、身份、文件路径或原始 logits。

```powershell
.\ai-service\.venv\Scripts\python.exe -m emoji_ai.cli benchmark --profile standard --manifest ai-service/models/manifest.json --model-dir ai-service/models --input "<local-approved-image>" --repeats 30 --threshold 0.7 --detection-threshold 0.85
.\ai-service\.venv\Scripts\python.exe -m emoji_ai.cli benchmark --profile edge --manifest ai-service/models/manifest.json --model-dir ai-service/models --input "<local-approved-image>" --repeats 30 --threshold 0.7 --detection-threshold 0.85
.\ai-service\.venv\Scripts\python.exe -m pytest -q -c ai-service/pyproject.toml ai-service/tests
# 显式启用真实模型检查，否则这两项 skip，不能计为真实能力已通过。
.\ai-service\.venv\Scripts\python.exe -m pytest -q -c ai-service/pyproject.toml ai-service/tests --model-smoke-input "<local-approved-image>" --model-dir ai-service/models
```

脚本可重复指定 `--input`，但当前一次载入所有输入，只适用于小规模 smoke；后续视频/数据集 benchmark 需流式和标注评估。startup_ms 不含 Python 进程启动与顶层依赖 import；warm latency 是检测/对齐/分类/映射，不含网络/DB，不能当采样→入库 SLA。

分数规则：

- DeepFace 返回 emotion percent，转换 `[0,1]`，不二次 softmax；detector score 另存。
- 轻量模型末端为 Gemm/Identity、实测原始输出有负值，不是概率；明确稳定 softmax 后作模型分数，不称已校准概率。
- 七类只映射 happy/sad/angry/surprise(d)/neutral 五类；fear/disgust 的赢家拒识，不重新挑支持类别。
- no-face 返回空观测，不写 NEUTRAL；其他模型异常向上传播；过小人脸/低分有独立原因。
- 当前 0.7/0.85 是验证参数，不是未经质量评估就批准的生产默认。

实测证据、局限和未验收项见 `../docs/AI_MODEL_VALIDATION.md` 和最新 `../docs/AI_TEST_REPORT.md`。

## 4. 正式网页帧服务

按 `../docs/AI_BROWSER_CAPTURE.md` 注册服务器身份，复制 `browser.example.json`
到受限 `.local/browser-ai/config.json`，保存凭证到配置中的 `token_file` 后：

```powershell
.\ai-service\.venv\Scripts\python.exe -m emoji_ai.browser_service --config .local/browser-ai/config.json
```

服务不打开摄像头；学生网页仅上传定时单帧。默认edge、模型串行、队列最多1帧、
admission4、HTTP解析连接16、JPEG256KiB/1280×720，以上不是全班容量承诺。
元数据outbox TTL60秒，最终授权有效才入库；没有照片/视频缓存。

## 旧 CLI Worker（回归工具，非学生接入方式）

一个设备代表一个采集 source；每个节点进程显式选择 `edge` 或 `standard`。
管理员在原管理端注册设备，source alias 对应节点配置的 `sources` 键，
一次性签发凭证。旧任务创建/开始/暂停/停止API当前也仅管理员可写，
教师只读所属课堂；不再在产品网页提供公共摄像头表单，学生 JWT 不参与服务身份。

从仓库根目录运行（将 example 复制到被忽略的 `.local/worker.json` 并修改输入）：

```powershell
$env:AI_DEVICE_TOKEN_FILE = 'D:\emoji-classroom-final\.local\device.secret'
.\ai-service\.venv\Scripts\python.exe -m emoji_ai.worker --config .local/worker.json
# 有界文件 smoke
.\ai-service\.venv\Scripts\python.exe -m emoji_ai.worker --config .local/worker.json --duration 60
```

凭证不放命令参数、URL、源码或日志；节点配置和 RTSP URL 留在节点受限文件。
远程后端必须 HTTPS，证书校验开启，不跟随重定向。
USB / RTSP latest-frame 覆盖只保留内存最新帧；file 每采样一步读下一帧，
用于有界演示而非实时重放原视频时间。文件 EOF 终止任务，health=`eof`，
当前协议使用终止型 `failed` 状态，不自动循环采集。

每次观测先入 SQLite WAL/FULL outbox，再向有界批次 API 发布。
网络不确定时保留 event UUID 重试；只有 accepted/duplicate/filtered 回执才 ACK，
永久拒绝计数并丢弃，401/403 退出采集。队列最多 5000 条、50MiB payload，
TTL 15 分钟；主文件另有约 51MiB 页数硬上限，WAL 定期截断，不是整个目录精确 50MiB。
控制心跳/确认最多常规每 5 秒，租约 45 秒；
断网只在未到期租约内采样，到期释放输入，旧授权采样可按服务端窗口补交。
不保存原帧、crop、landmark、embedding，也不把缺模型降级成假数据。
