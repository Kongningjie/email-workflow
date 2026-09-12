# 邮件驱动测试计划自动化平台

从用户上传的 `.eml` 生成可审核、可追溯并可提交到测试管理平台的测试计划。当前仓库正在按 `docs/development/implementation-plan.md` 分阶段实现。

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
npm run build
```

涉及容器、数据库或部署配置时，还必须运行 `docker compose up -d --build`，确认三个服务健康，并执行 `docker compose exec -T app alembic check`。

清理过期邮件原文、规范化正文和证据摘录：

```powershell
uv run python -m email_workflow.cli cleanup --dry-run
uv run python -m email_workflow.cli cleanup
```

上传接口在邮件解析后同步执行一次结构化提取。未配置 `DASHSCOPE_API_KEY`，或模型调用、JSON Schema、Pydantic、证据校验失败时，接口仍会创建可人工填写的版本 1 空白草稿，并将邮件标记为 `extraction_failed`。

阶段 2 可用查询接口：

```text
GET /api/v1/test-plans
GET /api/v1/test-plans/{plan_id}
GET /api/v1/test-plans/{plan_id}/versions
GET /api/v1/test-plans/{plan_id}/versions/{version_number}
```
