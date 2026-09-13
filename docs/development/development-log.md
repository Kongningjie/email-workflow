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

## 2026-09-12 — 阶段 1：安全邮件导入与证据

- 目标：实现仅限 `.eml` 的安全导入、确定性证据切片和短期数据清理，并满足阶段 1 验收标准。
- 完成内容：新增上传外发确认、5 MiB 限制、扩展名与 MIME 校验、原文 SHA-256 去重及并发唯一约束处理；实现受限邮件结构、邮件头、MIME 深度与部件数检查，纯文本优先、HTML 主动内容及远程资源移除、引用分区、签名与声明清理、附件元数据隔离；生成带规范化偏移量和独立哈希的 EvidenceSegment；实现原文、清洗正文和附件清单的受控原子写入，以及应用启动和 CLI 的幂等保留期清理；新增导入和证据查询 API。
- 变更文件／模块：`src/email_workflow/api`、`application`、`domain/email.py`、`infrastructure/email_parser.py`、`import_repository.py`、`storage.py`、`main.py`、`cli.py`，以及配置、依赖、容器和阶段 1 测试。
- 数据库迁移：无；阶段 0 表结构已包含 ImportedEmail 和 EvidenceSegment 所需字段、约束及索引，`alembic check` 确认无漂移。
- 测试与结果：Python compileall、Ruff、mypy 通过；pytest 33 项通过（包含独立 PostgreSQL 的导入、并发去重、失败留存、硬拒绝不落盘、证据及保留期测试）；八封黄金邮件解析通过；前端 lint/typecheck/test/build 与 npm audit 通过；Compose 三服务健康，上传确认拒绝返回 422 且不落库，首次导入返回 201，重复导入返回 200 和原 ID，导入／证据查询、HTML 远程资源移除、日志泄露检查及清理 dry-run 实机通过。
- 与冻结方案的偏差：无。
- 遗留问题：阶段 1 无阻断项；显式重新处理失败导入按冻结计划留待后续动作接口实现。
- 下一步：推送经 Review 的阶段 1 功能分支；进入阶段 2 的单次 LLM 结构化提取与草稿生成。

## 2026-09-12 — 阶段 2：单次 LLM 结构化提取与草稿

- 目标：实现一次受控 DashScope 结构化提取、可信证据重建和版本 1 草稿生成，并在所有提取失败场景安全降级。
- 完成内容：建立 Pydantic 严格提取 Schema、StructuredRequirementExtractor 协议、FakeExtractor 和基于 OpenAI Python SDK 的 LLMExtractor；采用 DashScope OpenAI-compatible Chat Completions、`json_schema`、关闭思考、60 秒超时、零 SDK 重试且不设置 `max_tokens`；仅向模型发送临时 evidence ID、清洗摘录和白名单字典；实现未知证据整体拒绝、证据边界与哈希重建、无证据事实清空、字典别名映射、允许的确定性派生、生成规模校验、RFC 8785 内容哈希、Prompt 版本／哈希及不可变版本 1；无 Key、超时、限流、服务异常、拒答、无效结构和证据失败均创建可人工填写的空白草稿；新增计划列表、详情和版本查询 API。
- 变更文件／模块：`domain/plan.py`、`application/extraction.py`、`plan_generation.py`、`plans.py`、`infrastructure/llm.py`、`plan_repository.py`、计划 API／Schema、应用装配、Prompt 配置和阶段 2 测试。
- 数据库迁移：无；阶段 0 已创建 TestPlan 和 TestPlanVersion，`alembic check` 确认无结构漂移。
- 测试与结果：Python compileall、Ruff、mypy 通过；pytest 51 项通过、1 项 live LLM 按门禁跳过，覆盖 FakeExtractor 成功／超时／限流／异常／无效结构、未知证据、无证据事实、规模限制、证据篡改、并发去重、版本 1 持久化及 OpenAI SDK 严格 Schema 请求；前端 lint/typecheck/test/build 及 npm audit 通过；Compose 无 Key 实机链路生成 `extraction_failed` 空白草稿，首次／重复上传和计划查询状态正确，重复上传未产生第二次模型调用日志，日志未出现邮件正文。
- 与冻结方案的偏差：无。
- 遗留问题：真实 DashScope live LLM 指标评测未自动执行，按冻结要求留待配置有效 Key 后人工显式触发；同步调用仍可能使上传等待至 60 秒。
- 下一步：推送经 Review 的阶段 2 功能分支；进入阶段 3 的规则、版本与人工 Review。

## 2026-09-13 — 阶段 3：规则、版本与人工 Review

- 目标：实现确定性规则校验、不可变完整快照版本、乐观并发控制以及送审、退回和批准闭环。
- 完成内容：实现由 `rules/v1.yaml` 驱动的 Blocking、Warning、Info 规则引擎及证据完整性、重复用例、引用正文和提示注入检测；校验批次与规则问题完整持久化，Blocking 送审失败时仍保留结果；保存采用 RFC 8785 和 SHA-256，仅当前内容变化时增版，要求 `base_version` 并使用行锁解决并发写入；服务端重建来源元数据，用户修改标记为 `user_provided`；实现待审内容锁定、退回意见必填、9 位数字工号、批准前逐条确认当前校验 Warning、每版本唯一审核决定和重复请求幂等；新增阶段 3 五个动作／查询 API。
- 变更文件／模块：`application/rules.py`、`application/workflow.py`、计划 API／Schema、领域规模约束、应用装配、数据库模型、README 和阶段 3 测试。
- 数据库迁移：新增 `20260913_0002`，允许持久化 Info、为规则问题增加建议字段、增加每版本唯一审核决定约束，并移除会阻止合法内容回退版本的内容哈希唯一约束。
- 测试与结果：Ruff、mypy 和专项／全量 pytest 通过；独立 PostgreSQL 覆盖无变化保存、真实并发冲突、待审锁定、Blocking 持久化、Warning 确认、审核幂等、退回再编辑及批准后改动失效；Alembic 全新升级、增量回滚、再次升级和结构漂移检查均通过。
- 与冻结方案的偏差：无。
- 遗留问题：平台报文硬契约和接近字段上限规则依赖阶段 4 映射配置，按计划在阶段 4 启用；真实 LLM 测试仍按显式门禁执行。
- 下一步：完成容器端到端冒烟和推送前 Review；随后进入阶段 4 的 Mock Gateway、预览与提交。

## 2026-09-13 — 阶段 4：Mock Gateway、预览与提交

- 目标：实现与内部计划快照隔离的平台 DTO、二次确认、HMAC 幂等提交，以及不确定结果的对账和受控重试。
- 完成内容：新增版本化平台字段上限和启动校验；统一 RFC 8785 canonical bytes、SHA-256、幂等键及 HMAC 输入；实现平台 DTO 与领域／值域映射，确保报文不包含邮件、证据、Prompt、开放问题或 Review 内容；实现独立 Mock Gateway 的 validate、submit、status、签名／正文哈希／五分钟时间窗校验及成功、重复、4xx、5xx、超时、查询成功／失败／not_found 场景；实现仅批准版本可预览、规则与 Warning 再核对、Mock validate、15 分钟令牌哈希存储、服务端报文重建、一次性确认、提交尝试记录、明确失败、不确定状态、对账和原身份重试；明确失败后允许修改并重新 Review，`submitted` 保持终态。
- 变更文件／模块：平台领域 DTO、映射、连接器、签名、提交服务、Mock Gateway、提交 API／Schema、应用装配、映射配置、README 和阶段 4 测试。
- 数据库迁移：无；阶段 0 已预建 PayloadPreview、Submission 和 SubmissionAttempt 所需字段及关键唯一约束，现有 Schema 无漂移。
- 测试与结果：Ruff、mypy、全量 pytest（68 passed、1 skipped、总覆盖率 86%）通过；前端 ESLint、TypeScript、Vitest、生产构建与 npm audit（0 vulnerabilities）通过；容器内 Alembic 结构漂移检查和应用／Mock Gateway 健康检查通过；真实 HTTP 冒烟覆盖 Gateway 校验、HMAC 提交、重复去重、状态查询和超时转 unknown。专项测试覆盖 canonical 向量、字段／集合上限、敏感字段排除、HMAC 错误与过期、Gateway 幂等、成功及重复确认、不同确认声明冲突、4xx、5xx／unknown、查询成功／失败／not_found、重试参数复用和终态锁定。
- 与冻结方案的偏差：无。
- 遗留问题：真实企业测试管理平台连接器不在 MVP 范围；Mock Gateway 状态为本地进程内测试数据，服务重启后清空。
- 下一步：进入阶段 5 前端实现。

## 2026-09-13 — 阶段 5：现代简约前端

- 目标：完成冻结的五个页面和从邮件导入到平台结果的前端闭环，保证桌面、平板与窄屏基本可用。
- 完成内容：以 React Router 组织邮件导入、计划列表、计划编辑与证据、规则审核、报文预览与提交五页；新增统一 fetch 客户端与错误结构，集中处理请求 ID、409 和安全消息；使用 React Hook Form 实现领域、需求、用例和步骤嵌套编辑，允许保存未完成草稿并编辑计划／领域／用例待确认事项；实现来源徽标、证据纯文本抽屉、规则语义色、Warning 逐条确认、审核与提交操作者声明、提交状态、unknown 对账和明确 not_found 后重试；采用响应式卡片、移动导航、固定操作栏、焦点样式及无阻断窄屏布局。
- 变更文件／模块：前端 API 类型与客户端、基础组件、应用外壳、五个页面、样式、Vitest 组件测试、Playwright 主链路测试、README 和依赖锁文件。
- 数据库迁移：无。
- 测试与结果：Python compileall、Ruff、mypy、Alembic heads/history 通过；全量 pytest 68 passed、1 skipped，总覆盖率 86%；前端 ESLint、TypeScript、6 条 Vitest 组件测试、2 条 Microsoft Edge Playwright 浏览器测试、生产构建和 npm audit（0 vulnerabilities）通过。浏览器测试覆盖五页完整主链路及 390px 窄屏布局，组件测试覆盖上传确认、列表状态、嵌套编辑、版本冲突、Warning 确认和 unknown 重试条件；Docker 同源页面完成桌面与窄屏视觉检查。
- 与冻结方案的偏差：无；Playwright 仅为开发测试依赖并复用系统 Edge，生产容器不增加 Node 常驻服务。
- 遗留问题：真实模型评测和八封黄金样例的最终验收报告按计划留在阶段 6。
- 下一步：进入阶段 6 验收与交付。

## 2026-09-13 — 阶段 6：验收与交付

- 目标：完成冻结的全量门禁、八封黄金邮件、真实模型指标、安全留存和文档一致性验收。
- 完成内容：建立八封 live LLM 可重复评测与 46 项明确事实基线；针对真实模型暴露的证据编号污染、领域／测试类型混淆、项目编码遗漏、唯一领域负责人关联和规模边界超时，收紧 JSON Schema 与 Prompt；Prompt 升级至 `1.5.0`；增加八封安全解析固定契约、DashScope OpenAI-compatible Base URL 启动校验和宿主机 `.env.example`；完成用例人工分级并形成阶段 6 验收报告。
- 变更文件／模块：`config/prompts/extraction-v1.yaml`、提取领域 Schema、LLM 请求封装、配置校验、黄金样例与 live 测试、`.env.example`、README 和 `docs/reports/phase-6-acceptance-report.md`。
- 数据库迁移：无；容器内 `alembic check` 确认无结构漂移。
- 测试与结果：领域召回 100%（8/8）、明确关键事实准确率 100%（46/46）、关键事实编造 0、结构化输出 8/8；Python 77 项通过、1 项默认 live 跳过；前端 6 项组件测试和 2 项浏览器测试通过；三服务健康，留存、日志脱敏、密钥隔离和文档一致性检查通过。
- 与冻结方案的偏差：无；用例人工分级没有通过率门槛，结果如实记录为 0 组可用、6 组需修改、2 组不可用。
- 遗留问题：真实模型非确定性；用例质量仍需人工 Review；边界样例可能产生会被 `domain.unique` Blocking 拦截的重复领域。
- 下一步：完成推送前独立 Review，质量门禁保持通过后推送阶段 6 功能分支。
