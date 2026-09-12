# 07. Mock 测试管理平台契约

## 连接器

```python
class TestManagementConnector(Protocol):
    async def validate_payload(...) -> ValidationResult: ...
    async def submit_plan(...) -> SubmissionReceipt: ...
    async def get_submission_status(...) -> SubmissionStatus: ...
```

一期只实现 `MockTestManagementConnector` 和独立本地 Mock Gateway，不实现 Kiwi TCMS 或企业 UTP。

## Gateway 接口

```text
POST /mock/v1/test-plans/validate
POST /mock/v1/test-plans
GET  /mock/v1/submissions/{submission_request_id}
```

- validate 只校验，不创建计划。
- submit 必须携带幂等键、请求 ID和 HMAC 签名。
- status 用于 `unknown` 对账。
- 测试场景可模拟成功、幂等重复、校验失败、超时、查询后成功／失败和 `not_found`。

## 平台报文

包含契约版本、内部计划 ID和版本号；计划名称、项目、需求编号；测试类型、阶段、轮次、优先级和版本；计划日期、目标、范围、环境、风险和依赖；领域编码、负责人、工号、执行日期、范围和需求；用例标题、目标、前置条件、步骤、测试数据、预期结果和优先级。

禁止包含原始邮件、正文、附件、证据摘录及定位、Prompt、模型原始响应、`open_questions`、`unresolved_fields`、Review 意见、API Key 或 HMAC 密钥。内部 TestPlanVersion 与平台 DTO 必须分离。

## Canonical JSON 与签名

- canonical JSON 统一采用 RFC 8785 和 UTF-8。
- 主应用与 Gateway 共享 canonicalization 模块和测试向量。
- 预览哈希、确认哈希、幂等键和 HMAC 均基于相同 canonical bytes。

请求头至少包含 `X-Key-Id`、`X-Timestamp`、`X-Content-SHA256`、`X-Signature`、`Idempotency-Key`、`X-Submission-Request-Id`。

HMAC-SHA256 输入覆盖 HTTP 方法、路径、时间戳、幂等键、请求 ID和正文哈希。Gateway 拒绝签名错误、哈希不一致和超过五分钟的请求。密钥只通过环境变量注入。

## 幂等、失败与对账

- `submission_request_id` 在发送前生成。
- 幂等键由计划 ID、版本号和 `payload_sha256` 确定性生成。
- 相同幂等键返回首次结果，不重复创建。
- 明确 4xx 进入 `submission_failed`；连接中断、超时或 5xx 进入 `unknown`。
- `unknown` 必须先查询；成功进入 `submitted`，明确失败进入 `submission_failed`。
- Gateway 明确返回 `not_found` 后才允许人工重试。
- 重试使用完全相同的版本、报文、请求 ID和幂等键。
- 业务字段错误必须修改计划、重新 Review 和确认。
