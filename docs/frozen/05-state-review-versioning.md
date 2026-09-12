# 05. 状态机、版本与人工 Review

## TestPlan 状态机

```text
draft
→ pending_review
→ revision_requested / approved
→ submitting
→ submitted / submission_failed / unknown
```

- 提取成功或失败都会创建 `draft`；失败时为空白草稿。
- 规则问题独立保存，不设置 `validation_failed`。
- `pending_review` 内容锁定。
- `revision_requested` 修改后创建新版本，再次校验送审。
- `approved` 绑定确切版本；修改会创建新版本并回到 `draft`。
- 二次确认后进入 `submitting`。
- `unknown` 只能先对账。
- `submitted` 是终态，不允许修改、撤销、覆盖、克隆或关联替代计划。

## 不可变版本

- 初次草稿为版本 1。
- 显式保存时对业务内容执行 RFC 8785 canonicalization 与 SHA-256。
- 仅哈希变化时创建新版本；无变化保存不增版。
- 每版保存完整快照，不保存增量补丁。
- 创建版本必须携带 `base_version`；并发冲突返回 HTTP 409。
- 旧版本永久只读。
- 用户修改字段后来源标记为 `user_provided`；旧证据可保留参考，但不得声称修改值来自邮件。

## 送审与 Review

- 送审前重新校验；存在 Blocking 时拒绝进入 `pending_review`。
- 只支持 `revision_requested` 和 `approved`。
- 退回必须填写意见。
- 批准必须填写操作者姓名和 9 位数字工号，逐条确认 Warning；批准意见可选。
- Review 显示版本、哈希、来源、证据、默认值及全部规则问题，并在提交时重新核对版本和哈希。
- 每个版本只允许一个最终有效决定，重复请求保持幂等。
- 修改产生新版本后，旧批准和 Warning 确认失效。

## 操作者身份边界

项目没有用户、登录、租户或权限模块。批准和提交时手工填写的姓名、工号只是不可变审计声明，不能证明身份真实，也不提供授权控制。普通导入、编辑和自动状态变化不记录操作者身份。

## 二次确认

- 只有当前 `approved` 版本可以生成平台报文预览。
- 预览前重新运行规则、映射和 Mock validate。
- 预览返回格式化报文、canonical JSON、`payload_sha256` 和 15 分钟有效的一次性确认令牌。
- 确认只接受令牌、报文哈希、操作者姓名和 9 位数字工号。
- 服务端重新读取批准版本并重新生成报文；版本、批准或哈希变化均拒绝。
- 前端不能提交自行修改的平台 JSON。
- 令牌使用后失效；重复确认返回已有 Submission。
