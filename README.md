# 邮件驱动测试计划自动化平台

从用户上传的 `.eml` 生成可审核、可追溯并可提交到测试管理平台的测试计划。当前仓库已完成一期 MVP 阶段 6 验收，详细结果见 `docs/reports/phase-6-acceptance-report.md`。

## 本地开发

```powershell
uv sync
uv run alembic upgrade head
uv run uvicorn email_workflow.main:app --reload
```

前端开发：

```powershell
cd frontend
npm install
npm run dev
```

完整环境：复制 `.env.example` 为 `.env` 后运行 `docker compose up --build`。

## 质量门禁

提交代码前必须执行：

```powershell
uv run python -m compileall -q src tests
uv run ruff check .
uv run mypy src tests
uv run pytest
uv run alembic heads
uv run alembic history

cd frontend
npm run lint
npm run typecheck
npm run test
npm run test:e2e
npm run build
```

涉及容器、数据库或部署配置时，还必须运行 `docker compose up -d --build`，确认三个服务健康，并执行 `docker compose exec -T app alembic check`。

清理过期邮件原文、规范化正文和证据摘录：

```powershell
uv run python -m email_workflow.cli cleanup --dry-run
uv run python -m email_workflow.cli cleanup
```

上传接口在邮件解析后同步执行一次结构化提取。未配置 `DASHSCOPE_API_KEY`，或模型调用、JSON Schema、Pydantic、证据校验失败时，接口仍会创建可人工填写的版本 1 空白草稿，并将邮件标记为 `extraction_failed`。

真实模型评测默认关闭。配置本地 `.env` 后可显式运行八封黄金邮件评测：

```powershell
$env:RUN_LIVE_LLM_TESTS='1'
uv run pytest tests/test_llm_live.py -s
```

评测对每封邮件只调用一次模型，并断言领域召回率、明确关键事实准确率和关键事实编造指标；它不属于常规 CI 门禁。

计划查询与阶段 3 工作流接口：

```text
GET /api/v1/test-plans
GET /api/v1/test-plans/{plan_id}
GET /api/v1/test-plans/{plan_id}/versions
GET /api/v1/test-plans/{plan_id}/versions/{version_number}
POST /api/v1/test-plans/{plan_id}/versions
POST /api/v1/test-plans/{plan_id}/validate
POST /api/v1/test-plans/{plan_id}/submit-for-review
POST /api/v1/test-plans/{plan_id}/reviews
GET /api/v1/test-plans/{plan_id}/reviews
POST /api/v1/test-plans/{plan_id}/payload-previews
POST /api/v1/test-plans/{plan_id}/submissions
GET /api/v1/test-plans/{plan_id}/submissions
GET /api/v1/submissions/{submission_id}
POST /api/v1/submissions/{submission_id}/reconcile
POST /api/v1/submissions/{submission_id}/retry
```

保存完整计划快照时必须携带 `base_version`；内容哈希未变化不会新增版本，并发基线冲突返回 409。送审会重新运行版本化确定性规则，Blocking 阻止状态变化，Warning 必须在批准请求中通过当前 `validation_run_id` 和问题 ID 逐条确认。审核操作者工号只接受 9 位数字。

只有当前批准版本可以生成平台报文预览。预览返回服务端生成的报文、canonical JSON、SHA-256 和 15 分钟一次性确认令牌；确认接口不接受客户端自定义平台 JSON。Mock Gateway 使用 HMAC-SHA256、五分钟时间窗和确定性幂等键；明确 4xx 记为 `submission_failed`，网络／超时／5xx 记为 `unknown`，后者必须先对账且平台明确返回 `not_found` 后才能原参数重试。

前端提供邮件导入、计划列表、计划编辑与证据、规则审核、报文预览与提交五个页面。组件测试使用 Vitest，浏览器主链路使用 Playwright 并复用本机 Microsoft Edge；生产环境仍由 FastAPI 同源提供静态构建，不增加常驻 Node 服务。
