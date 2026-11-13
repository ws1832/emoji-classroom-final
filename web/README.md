# 课堂三端 Web

Vue3、Naive UI、Pinia、Vue Router、Axios、Vite；Node.js >=22，pnpm9。

```powershell
pnpm install --frozen-lockfile
pnpm dev
pnpm run test:auth
pnpm run test:camera
node --test tests/session-date.test.mjs
pnpm build
```

本机localhost:3100，/api/v1代理9999，/ai-stream/frames代理独立AI9998。开发Vite仅本机监听、不自动打开浏览器；生产用dist+可信HTTPS，不公开开发服务器。
`.env*`仅公开构建配置，禁止加入服务凭证/密码。

学生 `/student/classroom`：原MANUAL+可选本机摄像头；个人历史只有手动记录。
教师 `/teacher/classroom`：所授历史/统计及只读匿名状态。
管理员 `/classroom/dashboard`：全局工作台，没有“我的课堂”。服务器生成能力并强制权限，隐藏菜单不是授权。

摄像头getUserMedia免安装，不采音频/录像；内存JPEG上传独立服务，bcc只内存，aic不入前端。停止/后台/离开/登出释放track，改密撤销旧JWT并退出；随机reset密码一次性弹窗、关闭清除、不持久存储。

[项目启动](../README.md)、[AI服务](../docs/AI_SERVICE.md)、[摄像头手册](../docs/AI_BROWSER_CAPTURE.md)。
