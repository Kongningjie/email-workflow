# 03. Workflow 与 LLM 契约

## 编排边界

项目使用普通 Python Workflow，不使用 AgentScope 或多 Agent。

```text
ParsedEmail
→ EvidenceSegmenter
→ StructuredRequirementExtractor
→ ExtractionValidator
→ TestPlanDraftBuilder
→ EvidenceRebuilder
→ TestPlanRuleEngine
→ WorkflowResult
```

Workflow 只负责固定顺序编排、输入输出类型、安全问题汇总、提取失败处理、来源校验和草稿生成。权限、数据库事务、Review、签名及平台提交由服务层负责。

## 提取器

领域层依赖 `StructuredRequirementExtractor` 协议，提供 `FakeExtractor` 与 `LLMExtractor`。LLM 只接收清洗后的邮件头和证据片段，只返回 Pydantic 结构；它没有工具、网络搜索、文件、数据库、记忆、Review 或提交权限。

## 模型与 SDK

- OpenAI Python SDK 作为客户端。
- 实际服务为阿里云百炼 DashScope OpenAI-compatible Chat Completions。
- 使用 `DASHSCOPE_API_KEY`、`DASHSCOPE_BASE_URL`。
- 模型为 `qwen3.7-plus-2026-05-26`。
- 关闭思考模式，使用严格 JSON Schema 和 Pydantic 解析。
- 不设置 `max_tokens`，避免结构化 JSON 被截断。
- 不调用 OpenAI API，不使用 `OPENAI_API_KEY`。

## 单次调用策略

- 每次 Workflow 最多调用一次，超时 60 秒，不自动重试、切换模型或二次修复 JSON。
- `temperature=0.1`；若兼容接口不支持则省略，并以适配器契约测试和 ADR 记录为准。
- 超时、限流、服务异常、拒答、无效 JSON、Schema 或 Pydantic 失败时，创建可人工填写的空白 `draft`。
- 失败只保存错误分类和脱敏摘要，不保存模型原始响应。

## 生成规模

- 最多 10 个领域。
- 每领域最多 20 条用例。
- 整个计划最多 100 条用例。
- 每条用例最多 20 个步骤。
- 超出上限不得静默丢弃，必须形成待确认问题。

JSON Schema 与 Pydantic 实施相同上限。

## 证据与 Prompt 防护

- 模型只能引用本次提供的临时 `evidence_id`。
- 模型不得输出正式数据库 ID、偏移量、摘录或哈希。
- 未知 evidence ID 导致整个提取结果失败。
- 正式 EvidenceReference 由可信代码重建。
- 事实只能来自邮件、人工补充或白名单确定性配置。
- 系统提示词是仓库内版本化模板，邮件片段仅作为结构化 JSON 数据。
- 邮件中的命令、角色声明和“忽略之前指令”均视为普通数据。
- 确定性注入检测只产生 Warning，安全性不依赖检测器。
- 计划版本保存 `prompt_version` 与模板哈希，不保存完整 Prompt。

## 日志与测试

日志只记录模型 ID、耗时、token 用量、供应商请求 ID和结果状态，不记录正文、Prompt、证据摘录、API Key 或原始响应。

默认 pytest 和 CI 不访问网络。真实模型测试必须标记 `live_llm`，并同时满足 `RUN_LIVE_LLM_TESTS=1` 和存在有效 `DASHSCOPE_API_KEY`。
