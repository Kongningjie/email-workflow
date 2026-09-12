# 09. 部署、存储与保留期

## 部署目标

Docker Compose 单机开发／演示环境包含主应用、独立 Mock Gateway 和 PostgreSQL；不包含 Redis、Celery、反向代理、云存储或 Kubernetes。

服务通过内部网络通信。DashScope Key、HMAC 密钥及环境差异配置通过环境变量或本地 `.env` 注入，仓库只提供 `.env.example`。

## 技术基线

- Python 3.12、`uv`、`src/` 布局。
- FastAPI、Uvicorn、Pydantic v2、pydantic-settings。
- SQLAlchemy 2 异步模式、asyncpg、Alembic。
- PostgreSQL 16，唯一正式数据库。
- 标准库 `email`、`nh3`、OpenAI Python SDK、httpx、PyYAML。
- pytest、pytest-asyncio、pytest-cov、Ruff、mypy。
- React 前端见 `08-api-and-ui.md`。

依赖补丁版本由锁文件固定。

## 数据库与 Workflow

- 主键 UUID；时间戳 UTC；业务计划日期使用 PostgreSQL `date`。
- 计划快照为经 Pydantic 验证的 JSONB。
- 状态、版本、哈希、幂等键、请求 ID及外部 ID使用独立列和必要唯一约束。
- 测试使用独立 PostgreSQL 测试库，不用 SQLite 替代。
- 上传请求同步完成解析、切片、一次模型调用、证据重建、规则和版本保存。
- 不使用 Celery、Redis 或应用内后台队列，不自动重试模型。

## 保留期与清理

- 原始 `.eml` 和清洗正文：24 小时。
- `safe_excerpt`：90 天。
- 邮件元数据、哈希、证据定位、计划版本、Review、Submission 和审计：长期保留。

到期后置空／删除内容并记录 `purged_at`，不得破坏关联记录。“长期”表示 MVP 不自动过期。

清理由应用启动时的幂等任务、显式管理命令及可选容器外部定时调用完成。清理提供 dry-run 和独立测试，且只能处理配置数据目录内的文件。
