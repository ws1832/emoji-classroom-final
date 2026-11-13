# AI 模型 P1 可运行性验证

日期：2026-11-11。**历史P1结论仅为两条CPU路线在本机可安装、离线检测/分类；
当时尚未选定默认，不是课堂准确率或最终D验收。当前默认已选edge，见下方修订说明。**

**历史P1报告：** 以下数字和当时决策保留作证据，不表示当前产品尚未实现。
2026-11-13已选edge作工程默认、standard作可选，学生网页链路已实现并有本机硬件短测；
最新服务事实见 `AI_SERVICE.md`，最新回归/现场缺口见 `AI_TEST_REPORT.md`。

## 1. 版本与来源核实

读取了官方 PyPI JSON、实际发行 wheel 源码，不将 GitHub master 能力误认为已发布：

- DeepFace **0.0.104** wheel 上传时间为 **2026-11-04**。该实际发行版已有显式 ONNX engine、YuNet detector、Emotion ONNX；本轮指定 CPU 后真实推理成功。
- FER **25.10.3** wheel 上传时间为 **2025-10-21**，实际依赖同时包括 TensorFlow、facenet-pytorch、moviepy 等。不能仅凭名称或默认 CNN 判断整体部署轻量；本轮未安装/推理 FER，不宣称其质量比另两条路线差。
- OpenCV 固定 **4.11.0.86** 而非自动跟随最新版，NumPy 2.2.6、ONNX Runtime 1.31.1。当前仅验证 Windows CPython 3.11 CPU wheel。
- OpenCV Zoo 固定 commit `48b10fa505aeb51fbd127fc60a5c660040e823b7`，两个模型 SHA-256 与 Git LFS pointer 一致；DeepFace Emotion release 也固定 SHA-256，详见 `ai-service/models/manifest.json`。
- 原始元数据、素材、运行日志留本地；正式仓库保留脚本、platform lock、manifest 和匿名结果，不包含模型文件。

## 2. 真实验证方法

Windows、CPython 3.11.15、CPU；单一 512×512 OpenCV 官方样例图片，另有 640×480 合成全黑无脸帧。素材未提交。这是 runtime smoke，不是课堂样本，不提供标注准确率。

两条路线均执行：独立环境安装 → `pip check` → 下载/哈希核验 → 离线启动 → warmup 2 次 → 同样例重复 30 次 → blank-frame 检查。显式 `--model-smoke-input` 的测试禁止临时权重下载并检查输出只含匿名表情/质量。

## 3. 输出与预处理核验

| 路线 | 处理 | 分数 |
| --- | --- | --- |
| standard | DeepFace emotion-only，YuNet、align=True，48×48 gray emotion 网络 | 发行源码的百分比输出按总和归一 `[0,1]`，不二次 softmax |
| edge | OpenCV YuNet 五点，112×112 非反射 similarity；BGR→RGB、`(x/255-.5)/.5`、NCHW | 图末端 Gemm→Identity；实际 raw 输出含负值，按 logits 稳定 softmax |

edge 标签顺序 `angry/disgust/fearful/happy/neutral/sad/surprised` 与 DeepFace 不同，不能共用未声明顺序。fear/disgust 拒识；无脸不补 NEUTRAL；异常不吞作无脸。score 不是已校准真实心理状态概率。

### 关键发现：检测器包装影响阈值

同样例检测阈值 **0.90**：

- OpenCV 直接 YuNet 能检出；直接 DeepFace detector forward 的 score 约 0.909。
- DeepFace **完整 analyze 流程**返回 FaceNotDetected；阈值调为 **0.85** 后检测成功、返回 face_confidence 0.87。

完整流程包含额外处理，不应认为同一底层权重就有完全相同的检测行为。本轮保留 0.90 拒识证据，CLI 增加显式 detection-threshold；未静默切模型或调低生产阈值。后续需按 profile 对真实场景评估阈值和漏检/误检。

## 4. 同参数性能 smoke

同 emotion threshold=0.70、detection threshold=0.85、最小脸 48px、CPU，30 次相同输入：

| 指标 | DeepFace Emotion + YuNet / ORT | YuNet + MobileFaceNet / OpenCV DNN |
| --- | ---: | ---: |
| 模型初始化及校验 ms | 696.636 | 19.518 |
| warm p50 ms | 22.139 | 15.235 |
| warm p95 ms | 45.974 | 16.276 |
| warm p99 ms | 58.726 | 16.391 |
| 检出观测 / 30 次 | 30 | 30 |
| 通过阈值 / 30 次 | 30 | 30 |
| 全黑帧观测 | 0 | 0 |
| detector + classifier 文件量 | 约 6.18 MB | 约 5.02 MB |

初始化不含解释器和顶层 import；warm 不含网络、排队和入库。本机有其他进程，运行次数少且输入重复；这些数字不证明模型准确、能识别教室后排、多流性能或端到端延迟。两个模型对该未标注样例可能输出不同表情，confidence 高也不能证明正确。

## 5. 许可与可维护性

- DeepFace 库 MIT；模型 release README 明确要求外部研究模型继承其许可。Emotion 权重具体训练来源/商业授权仍需完成发布审核，库许可不自动覆盖全部权重。
- YuNet 随目录 MIT 许可，原文保留 `ai-service/third_party/YuNet-LICENSE.txt`。
- OpenCV Zoo 仓库 Apache-2.0，expression README 声明该目录文件 Apache-2.0；固定 commit 下 README 链接的目录 LICENSE 返回 404。保留上游根 LICENSE，记录缺失，发布前进一步核查表情权重/训练数据条件，不能将 README 的精度数字套作课堂效果。
- 模型不随 Git 或后端 Docker context 打包；显式准备、hash 校验、一个 profile 一个进程，没有自动 engine/fake fallback。

来源标识（用于可复核，不依赖移动 master 作模型版本）：

```text
https://pypi.org/pypi/deepface/json
https://pypi.org/pypi/fer/json
deepface-0.0.104-py3-none-any.whl:
  deepface/commons/backend_utils.py
  deepface/modules/demography.py
  deepface/models/demography/onnx/Emotion.py
  deepface/models/face_detection/onnx/YuNet.py
https://github.com/opencv/opencv_zoo/tree/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/facial_expression_recognition
https://github.com/serengil/deepface_models/releases/tag/v1.0
```

## 6. 决策和下一道验证门

提交前测试：后端 **99 passed**；独立 AI **23 passed**（包括显式真实模型离线 smoke 两项，无 skip）；现有前端认证 **53 passed**、日期 **3 passed**。新增源码 Ruff 与格式检查通过。真实模型 smoke 使用准备好的本地权重，未启用摄像头或写入运行中的业务数据库。

**保留 standard + edge 两候选，不把 FER 强行加入 production，也不现在宣布 edge 或 standard 胜出。** DeepFace 当前发行版的 ONNX CPU 路线使“使用 DeepFace”与“轻量部署”并不互斥；最终以获准标注场景的质量、容量、稳定性和许可决定默认 profile。

后续必测：真实 USB/video→API→同表、多人/小脸/侧脸/遮挡/低光、quality confusion/macro-F1、按人/场景拆分防相邻帧泄漏、1/2/4 流、线程资源、2h soak、断网/重启、Windows/Linux/RTSP/MySQL。采样率/延迟指标仍为待验证目标，GPU/浏览器采集未验收。
