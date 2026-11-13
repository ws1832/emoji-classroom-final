# Emoji Classroom Emotion Checker

This repository extends Vue FastAPI Admin with shared classroom models, three role-separated Vue portals,
FastAPI/Tortoise APIs, and an independently deployed Python expression inference service.
Original MIT attribution is retained in LICENSE.

## AI implementation

Students capture timed JPEG frames using an ordinary webcam and browser `getUserMedia`; no local Python,
model, plug-in or capture agent is installed. The self-hosted `emoji_ai.browser_service` performs inference
and posts anonymous metadata to the existing API/database. No external LLM API is used.

- Default `edge`: OpenCV 4.11.0.86 YuNet + OpenCV Zoo MobileFaceNet expression FP32 ONNX, CPU OpenCV DNN.
- Optional `standard`: DeepFace 0.0.104 Emotion-only + YuNet, ONNX Runtime 1.31.1 CPU.
- FER was evaluated as an option, not installed or exposed as a supported runtime.
- AI results have null user IDs; no identity recognition, raw image/video retention or individual AI history.
- Administrators configure 5/10/15/30-second sampling (default 10); teachers view assigned classrooms read-only.
- Students authorize/stop only their own camera; manual emoji feedback remains available.

## Run locally on Windows

Requirements: Python 3.11, Node.js >=22, pnpm 9.15.9.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
# Set DB_ENGINE=sqlite and a private SECRET_KEY in .env.
.\.venv\Scripts\python.exe run.py
# Another terminal:
pnpm --dir web install --frozen-lockfile
pnpm --dir web dev
```

Web: localhost:3100; API/docs: localhost:9999/docs. The public development bootstrap is admin/123456,
only on an empty development database; production rejects default secrets. Password changes revoke old
JWT/camera grants and require login again. Reset passwords are randomly generated and displayed once.

Use only `python scripts/migrate.py` for committed Aerich 0 -> 1 -> 2 -> 3 migrations. Back up before upgrading;
do not combine reference SQL scripts with migrations. Production templates are `deploy/compose.yml` and
`deploy/compose.browser.yml`; Linux/Compose/TLS deployment still requires target-environment acceptance.

The maintained detailed documentation is in Simplified Chinese:

- [Quick start and project documentation](README.md)
- [Actual AI service/models](docs/AI_SERVICE.md)
- [Browser webcam integration](docs/AI_BROWSER_CAPTURE.md)
- [API integration](docs/AI_INTEGRATION.md), [operations](docs/AI_OPERATIONS.md)
- [Test evidence](docs/AI_TEST_REPORT.md), [final review](docs/FINAL_REVIEW.md)

Models, credentials, raw media, databases, local plans and runtime artifacts are not committed.
Smoke tests do not establish classroom accuracy, whole-class capacity or production readiness.
