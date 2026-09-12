# 开发日志

本文件按日期追加，禁止覆盖历史记录。

## 记录模板

### YYYY-MM-DD — 阶段／主题

- 目标：
- 完成内容：
- 变更文件／模块：
- 数据库迁移：
- 测试与结果：
- 与冻结方案的偏差：无／ADR 链接
- 遗留问题：
- 下一步：

## 2026-09-11 — 方案冻结

- 目标：完成 MVP 未决项访谈并形成 Coding 契约。
- 完成内容：创建冻结方案、编码规范、测试规范、ADR、实施计划和日志模板。
- 数据库迁移：无。
- 测试与结果：完成文档结构、冲突词和残留占位符检查。
- 与冻结方案的偏差：无。
- 遗留问题：进入 Coding 后记录实际依赖锁定版本和实现发现。
- 下一步：按阶段 0 初始化工程。

## 2026-09-11 — 阶段 0：契约与工程基线

- 目标：建立可运行、可迁移、可测试的全栈工程基线。
- 完成内容：初始化独立 Git 仓库与 `main` 分支；建立 Python 3.12／uv、FastAPI 主应用、独立 Mock Gateway、React／TypeScript／Vite 前端空壳和 Docker Compose；实现结构化日志、请求 ID、安全错误结构、启动配置校验；落地领域、值域、规则、Prompt 和平台映射版本化 YAML；加入八封虚构黄金 `.eml`。
- 变更文件／模块：`src/email_workflow`、`src/mock_gateway`、`frontend`、`config`、`tests/fixtures/eml`、容器与质量门禁配置。
- 数据库迁移：新增 `20260911_0001`，创建 11 张核心表及 UUID、外键、内容哈希、版本、工号和幂等约束。
- 测试与结果：Ruff、mypy、pytest（8 项）、compileall、Alembic heads/history/离线 PostgreSQL DDL、前端 lint/typecheck/test/build、npm audit、Compose 配置及本地主应用／Gateway／静态前端冒烟均通过。
- 与冻结方案的偏差：无。
- 遗留问题：宿主机 Docker Desktop 因其运行目录中的 `sailor-ingest.sock` 访问错误而崩溃，未能执行 Compose 容器实机启动；代码侧 `docker compose config` 已通过，待宿主机 Docker 修复后复验。
- 下一步：修复宿主机 Docker Desktop 后执行 Compose 实机冒烟；随后进入阶段 1。

## 2026-09-12 — 阶段 0：推送前 Review 与容器复验

- 目标：在首次推送远端前完成代码 Review、问题修复和完整质量门禁。
- 完成内容：修复 Dockerfile 在复制源码前安装本项目导致的干净构建失败；避免 SPA 回退吞掉未知 API 路径；统一 HTTP 404 安全错误；补全首版 Blocking、Warning、Info 规则元数据并校正派生值级别；增加目录和规则 ID 唯一性校验及回归测试；统一应用日志为 JSON 并关闭可能记录不可信 URL 的默认访问日志；补充质量门禁说明。
- 变更文件／模块：`Dockerfile`、`src/email_workflow/core`、`src/email_workflow/main.py`、`config/rules/v1.yaml`、`tests`、`README.md`。
- 数据库迁移：无新增迁移；在 PostgreSQL 16 容器中应用 `20260911_0001`，创建 11 张核心表，`alembic check` 无结构漂移。
- 测试与结果：Python 全部门禁通过，pytest 12 项通过；前端 lint/typecheck/test/build 通过，npm audit 为 0；Docker 镜像从零构建成功，主应用、Mock Gateway、PostgreSQL 均健康，API 和同源前端冒烟通过；应用日志为结构化 JSON，恶意查询参数未进入访问日志。
- 与冻结方案的偏差：无。
- 遗留问题：无阶段 0 阻断项。
- 下一步：推送已 Review 代码，随后进入阶段 1。
