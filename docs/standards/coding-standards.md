# 编码规范

## 通用原则

- 领域规则优先于框架便利性。
- Workflow、LLM、数据库、HTTP 和 UI 分层，不跨层调用。
- 所有外部输入先验证再进入领域层。
- 不吞异常，不在业务代码使用裸 `except`。
- 日志默认结构化，严格执行敏感数据最小化。
- 代码、类型和字段名使用英文；用户文案使用简体中文。

## Python

- Python 3.12，完整类型标注。
- Pydantic Schema、SQLAlchemy Model 和领域对象分开。
- API 路由只做协议转换；事务在服务层控制。
- Repository 不包含业务状态转换。
- 外部模型和平台通过 Protocol／适配器接入。
- 时间戳使用带时区 UTC；计划日期使用 `date`。
- UUID、哈希、幂等键和版本号不得由前端决定。
- canonical JSON 统一调用共享模块。
- Ruff 与 mypy 无错误后才允许合并。

## TypeScript／React

- 开启 TypeScript strict。
- 页面负责组合，业务交互封装为小型 hooks／services。
- 不引入全局状态库，除非未来有已证明的跨页面共享需求。
- 服务端规则为最终依据；前端校验只提供即时反馈。
- 请求统一经过轻量 fetch 封装，处理请求 ID、错误结构和 409。
- 禁止用 `dangerouslySetInnerHTML` 显示邮件或模型内容，证据仅以纯文本渲染。
- 组件遵守冻结的语义色、间距和可访问性要求。

## 配置与数据库

- 环境变量只承载环境差异和密钥。
- 领域、值域、规则元数据、Prompt 和平台映射使用版本化文件。
- 配置启动时一次性验证，失败则拒绝启动。
- 所有 Schema 改动必须有 Alembic migration。
- 关键不变量由数据库约束兜底。
- 不可变版本只插入，不原地更新业务内容。
- 状态变化使用事务和乐观并发控制。

## 安全编码

- 上传、路径、HTML、Header、URL、日志和异常均按不可信输入处理。
- 文件操作只能使用验证位于配置数据目录下的绝对路径。
- Mock Gateway 不得访问主应用邮件数据卷。
- LLM 输出必须验证 Schema、值域和 evidence ID。
- 提交创建只能由 SubmissionService 发起。
