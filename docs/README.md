# 邮件驱动测试计划自动化平台文档

本目录是项目一期 MVP 的设计、实施与验收依据。当前状态为 **已冻结，允许进入 Coding**。

## 阅读顺序

1. `frozen/01-mvp-scope.md`
2. `frozen/02-domain-model.md`
3. `frozen/03-workflow-and-llm.md`
4. `frozen/04-evidence-and-security.md`
5. `frozen/05-state-review-versioning.md`
6. `frozen/06-rule-engine.md`
7. `frozen/07-mock-platform-contract.md`
8. `frozen/08-api-and-ui.md`
9. `frozen/09-deployment-and-retention.md`
10. `frozen/10-acceptance-criteria.md`
11. `standards/` 下的工程规范
12. `development/implementation-plan.md`

## 文档效力

- `frozen/` 是产品行为、领域模型、接口边界和验收口径的主要契约。
- Coding 与冻结文档冲突时，以冻结文档为准。
- 确需改变已冻结决策时，先新增或更新 `decisions/` 下的 ADR，再同步更新所有受影响文档和测试。
- 低风险实现细节可由开发者决定，但必须满足一致性、安全边界和可测试性要求。
- `development/development-log.md` 只追加，不覆盖历史记录。

## 已明确废止的讨论方案

- 不使用 AgentScope，不实现多 Agent。
- 不调用 OpenAI API；OpenAI Python SDK 仅作为 DashScope 兼容接口客户端。
- 不实现用户、登录、租户或 RBAC 模块。
- 不使用服务端模板作为业务前端。
- 不实现计划替代、克隆或提交后修改。
- 不对落盘数据做应用层加密；该系统仅面向 MVP 开发与演示环境。
