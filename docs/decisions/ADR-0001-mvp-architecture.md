# ADR-0001：一期 MVP 总体架构

- 状态：Accepted
- 日期：2026-09-11

## 背景

项目需要从用户上传的测试需求邮件生成可追溯、可校验、需人工确认的测试计划，并通过 Mock 平台验证提交闭环。重点是产品链路与安全边界，不是 Agent 或企业身份平台。

## 决策

- 独立 FastAPI 主应用、精简 React SPA、PostgreSQL 和独立 Mock Gateway。
- Docker Compose 单机开发／演示部署。
- 普通确定性 Workflow，不使用 AgentScope 或多 Agent。
- 一次受控 LLM 调用；OpenAI Python SDK 调用 DashScope 兼容接口，模型为 `qwen3.7-plus-2026-05-26`。
- 不实现用户、登录、租户或 RBAC；批准和提交仅记录手工操作者声明。
- 计划采用不可变完整快照，所有事实保留证据来源。
- Blocking 不可豁免，Warning 逐条确认。
- 提交采用预览、一次性令牌、RFC 8785、SHA-256、HMAC-SHA256 和幂等键。
- 只接本地 Mock Gateway。
- 邮件原文与证据明文保存，限制为 MVP 演示环境。

## 结果

优点：依赖和状态边界清晰；模型权限极小；业务过程可复现；未来可替换模型和平台适配器。

代价：同步模型调用可能等待数十秒；没有真实身份认证；明文存储不适合生产敏感邮件；提交后修改和真实平台更新不在范围内。

## 被否决方案

- AgentScope／多 Agent：一次结构化提取没有自主规划需求。
- 纯规则提取：不能验证非固定邮件的核心价值。
- Celery／Redis：一期不值得增加部署状态。
- SQLite：与目标 PostgreSQL 行为不一致。
- OpenAI API：没有可用于开发测试的 OpenAI API Key。
- DashScope 原生 SDK：兼容接口可利用 OpenAI SDK 的 Pydantic 解析。
- 服务端模板或重型前端栈：前者不利于嵌套编辑，后者超出五页应用需要。
