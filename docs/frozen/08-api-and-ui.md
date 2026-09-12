# 08. 主应用 API 与前端

## API 原则

- API 前缀 `/api/v1`，OpenAPI 是联调契约。
- 查询使用资源接口，状态变化使用显式业务动作。
- 服务端是状态、规则、哈希和提交权限的唯一裁决者。
- 错误返回机器可读错误码、简体中文安全消息、字段路径和请求 ID，不暴露堆栈或敏感内容。

## 首版接口

```text
POST   /api/v1/imports
GET    /api/v1/imports/{import_id}
GET    /api/v1/test-plans
GET    /api/v1/test-plans/{plan_id}
GET    /api/v1/test-plans/{plan_id}/versions
GET    /api/v1/test-plans/{plan_id}/versions/{version}
POST   /api/v1/test-plans/{plan_id}/versions
POST   /api/v1/test-plans/{plan_id}/validate
POST   /api/v1/test-plans/{plan_id}/submit-for-review
POST   /api/v1/test-plans/{plan_id}/reviews
GET    /api/v1/test-plans/{plan_id}/reviews
GET    /api/v1/evidence/{segment_id}
POST   /api/v1/test-plans/{plan_id}/payload-previews
POST   /api/v1/test-plans/{plan_id}/submissions
GET    /api/v1/test-plans/{plan_id}/submissions
GET    /api/v1/submissions/{submission_id}
POST   /api/v1/submissions/{submission_id}/reconcile
POST   /api/v1/submissions/{submission_id}/retry
```

上传使用 multipart。创建版本必须带 `base_version`。Review 使用 `decision=approved|revision_requested`。预览不提交。提交只接受确认令牌、哈希和操作者声明，不接受客户端自定义平台 JSON。

## 前端范围与技术栈

页面控制为五个：邮件上传；计划列表；计划编辑与证据查看；Review；报文预览、提交及结果。

- React + TypeScript + Vite。
- React Router。
- Tailwind CSS。
- React Hook Form，仅用于复杂嵌套表单。
- Lucide 图标。
- 原生 `fetch` 与少量自建基础组件。

不引入 TanStack Query、Zod 前端 Schema、shadcn/ui、Redux、OpenAPI 客户端生成、Next.js、SSR、微前端、大型图表或动画库。

## 视觉与部署

- 浅色中性配色、单一强调色、大留白、清晰层级、轻边框、少阴影。
- 不用大面积渐变、玻璃拟态或无意义动画。
- 规则、来源和状态采用一致语义色。
- 桌面端优先，平板和窄屏基本可用。
- 长表单使用分区、折叠和固定操作栏。
- 保证键盘操作、焦点可见、表单标签和基础对比度。
- 开发时 Vite 代理 `/api`；生产构建由 FastAPI 同源提供。
- Docker Compose 不增加常驻 Node 服务，前端不得直接访问 Mock Gateway。
