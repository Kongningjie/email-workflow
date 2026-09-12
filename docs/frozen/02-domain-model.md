# 02. 领域模型与字段契约

## 聚合关系

```text
ImportedEmail 1 ── 1 TestPlan
TestPlan      1 ── N TestPlanVersion
TestPlanVersion 包含 N TestPlanDetail
TestPlanDetail  包含 N TestCaseDraft
```

## ImportedEmail

字段：`id`、`original_filename`、`subject`、`sender`、`recipients`、`sent_at`、`content_sha256`、`parse_status`、`extraction_status`、`safe_error_summary`、`created_at`、`raw_expires_at`、`purged_at`。不包含 `tenant_id` 或 `user_id`。

```text
uploaded → parsing → parsed / parse_failed
parsed → extracting → extracted / extraction_failed
```

## EvidenceSegment

字段：`id`、`source_item_id`、`section_type`、`segment_index`、`start_offset`、`end_offset`、`safe_excerpt`、`content_sha256`、`created_at`、`expires_at`、`purged_at`。

`section_type` 至少支持 `subject`、`sender`、`recipients`、`sent_at`、`current_body`、`quoted_body`。

## TestPlan

字段：`id`、`source_email_id`、`current_version`、`status`、`external_platform_id`、`created_at`、`updated_at`。不包含用户、租户或替代计划关系字段。

## 公共计划字段

- `plan_name`
- `project_name`
- `project_code`
- `requirement_ids`
- `test_type`
- `test_stage`
- `test_round`
- `priority`
- `test_version`
- `planned_start_date`
- `planned_end_date`
- `objective`
- `scope`
- `environment`
- `risks`
- `dependencies`
- `notes`
- `open_questions`
- `evidence_references`
- `details`

送审前必填：计划名称；项目名称或项目编码至少一个；测试类型；测试阶段；优先级；测试版本；合法起止日期；测试目标；总体范围；至少一个有效领域明细。

需求编号、测试轮次、环境、风险、依赖和备注为可选。必填事实缺失时进入 `open_questions` 并产生 Blocking。

## TestPlanVersion

字段：`id`、`test_plan_id`、`version_number`、`content`、`content_sha256`、`domain_catalog_version`、`value_catalog_version`、`prompt_version`、`prompt_sha256`、`created_at`。

业务内容使用经 Pydantic 验证的完整 JSONB 快照。规则结果、Review、平台预览和 Submission 独立保存并绑定版本。

## TestPlanDetail

送审前必须有效：`domain_key`、`domain_name`、`domain_code`、`owner_name`、`owner_employee_id`、`execution_start_date`、`execution_end_date`、`scope`、`requirements`、`test_cases`、`evidence_references`、`unresolved_fields`。

- 领域名称与编码只来自计划绑定的领域字典版本。
- 负责人和工号只来自邮件或人工补充；首版不设置默认负责人。
- 工号是字符串，必须匹配 `^[0-9]{9}$`，保留前导零。
- 未指定领域执行日期时，可继承计划日期并标记 `derived`。
- `requirements` 至少一项，且每项保存来源。
- `scope` 必须说明该领域测试内容，不能只重复领域名称。
- 每个领域送审前至少包含一条有效用例。

## TestCaseDraft

- `title`：必填。
- `objective`：必填。
- `preconditions`：列表，可为空。
- `steps`：有序列表，每步包含 `step_number` 与 `action`，至少一步。
- `test_data`：可为空。
- `expected_result`：必填。
- `priority`：必填，来自值域配置。
- `domain_key`：必填，必须等于父级领域。
- `evidence_references`：正式用例至少一项。
- `provenance`：必填。
- `open_questions`：列表，可为空。

一期不支持参数化、前后置用例依赖、自动化脚本、用例树、逐步骤预期结果或外部平台用例 ID。

## 来源类型

- `source`：邮件中直接存在。
- `user_provided`：用户编辑补充或修改。
- `derived`：白名单确定性规则生成。
- `model_suggestion`：模型基于邮件证据扩展的建议。
- `unresolved`：暂不能确认。

每条正式用例至少关联一个邮件证据锚点。`model_suggestion` 的引用只表示建议基于此需求产生，不表示邮件明确要求该用例。无任何邮件依据的泛化建议不进入正式草稿。

## ReviewRecord

字段：`id`、`test_plan_id`、`test_plan_version_id`、`content_sha256`、`operator_name`、`operator_employee_id`、`decision`、`comment`、`acknowledged_warning_ids`、`created_at`。

操作者姓名与工号是手工填写的审计声明，不代表认证身份。

## Submission

字段：`id`、`test_plan_id`、`test_plan_version_id`、`mapping_profile_version`、`payload_sha256`、`submission_request_id`、`idempotency_key`、`status`、`operator_name`、`operator_employee_id`、`confirmed_at`、`external_request_id`、`external_plan_id`、`safe_response_summary`、`created_at`、`finished_at`。

## 确定性默认值白名单

仅允许：由 `domain_key` 填充领域名称和编码；领域日期继承计划日期；用例继承父级 `domain_key`；计划名称由邮件主题生成草稿值；平台固定常量由映射配置填充。

项目、需求编号、测试类型、阶段、轮次、优先级、版本、计划日期、目标、范围、环境、风险和依赖不得猜测或默认。所有默认值标记为 `derived` 并在 Review 中显示。

## 初始配置

领域：`communication`／通信／`COMM`，`stability`／稳定性／`STAB`，`power`／功耗／`PWR`。首版不配置默认负责人。

测试类型：`functional`、`regression`、`smoke`、`performance`、`stability`、`compatibility`、`security`。

测试阶段：`component`、`integration`、`system`、`acceptance`。

优先级：`critical`、`high`、`medium`、`low`。

以上配置均包含内部值、显示名称、平台值、别名、启用状态和版本。未知值不得临时创造，必须进入待确认项。
