import { expect, test } from '@playwright/test'

const planId = '11111111-1111-4111-8111-111111111111'
const versionId = '22222222-2222-4222-8222-222222222222'
const now = '2026-09-13T04:00:00Z'

test('邮件导入到平台提交的五页主链路', async ({ page }) => {
  let status = 'draft'
  let version = 1
  const content = {
    plan_name: '通信回归测试计划', project_name: 'Atlas', project_code: 'ATLAS', requirement_ids: ['REQ-101'], test_type: 'functional', test_stage: 'system', test_round: '第一轮', priority: 'high', test_version: '1.0', planned_start_date: '2026-09-15', planned_end_date: '2026-09-20', objective: '验证通信主链路', scope: '通信功能', environment: '测试环境 A', risks: ['网络抖动'], dependencies: ['测试 SIM 卡'], notes: '', open_questions: [], evidence_references: [], field_metadata: {}, details: [],
  }
  const plan = () => ({ id: planId, source_email_id: '33333333-3333-4333-8333-333333333333', current_version: version, status, external_platform_id: status === 'submitted' ? 'PLAN-001' : null, created_at: now, updated_at: now, version: { id: versionId, test_plan_id: planId, version_number: version, content, content_sha256: 'a'.repeat(64), domain_catalog_version: '1.0.0', value_catalog_version: '1.0.0', prompt_version: '1.0.0', prompt_sha256: 'b'.repeat(64), created_at: now } })
  const validation = () => ({ id: '44444444-4444-4444-8444-444444444444', test_plan_id: planId, test_plan_version_id: versionId, content_sha256: 'a'.repeat(64), rule_set_version: '1.0.0', status: 'passed', blocking_count: 0, warning_count: 0, finished_at: now, issues: [] })
  const submission = () => ({ id: '66666666-6666-4666-8666-666666666666', test_plan_id: planId, test_plan_version_id: versionId, payload_preview_id: '77777777-7777-4777-8777-777777777777', mapping_profile_version: '1.0.0', payload_sha256: 'c'.repeat(64), submission_request_id: '88888888-8888-4888-8888-888888888888', idempotency_key: 'd'.repeat(64), status: 'submitted', operator_name: '王芳', operator_employee_id: '001234567', confirmed_at: now, external_request_id: 'REQ-001', external_plan_id: 'PLAN-001', safe_response_summary: '平台提交成功', finished_at: now, created_at: now })

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/api/v1/imports' && request.method() === 'POST') return route.fulfill({ json: { test_plan_id: planId, deduplicated: false, warnings: [] } })
    if (path === `/api/v1/test-plans/${planId}`) return route.fulfill({ json: plan() })
    if (path === `/api/v1/test-plans/${planId}/versions` && request.method() === 'POST') { version += 1; return route.fulfill({ json: { created: true, version: { ...plan().version, version_number: version } } }) }
    if (path === `/api/v1/test-plans/${planId}/submit-for-review`) { status = 'pending_review'; return route.fulfill({ json: validation() }) }
    if (path === `/api/v1/test-plans/${planId}/reviews` && request.method() === 'GET') return route.fulfill({ json: [] })
    if (path === `/api/v1/test-plans/${planId}/reviews` && request.method() === 'POST') { status = 'approved'; return route.fulfill({ json: { id: '99999999-9999-4999-8999-999999999999' } }) }
    if (path === `/api/v1/test-plans/${planId}/submissions` && request.method() === 'GET') return route.fulfill({ json: status === 'submitted' ? [submission()] : [] })
    if (path === `/api/v1/test-plans/${planId}/payload-previews`) return route.fulfill({ json: { id: '77777777-7777-4777-8777-777777777777', test_plan_id: planId, test_plan_version_id: versionId, content_sha256: 'a'.repeat(64), mapping_profile_version: '1.0.0', payload: { contractVersion: '1.0', planName: content.plan_name }, canonical_json: '{}', payload_sha256: 'c'.repeat(64), validation_status: 'valid', confirmation_token: 't'.repeat(43), expires_at: '2026-09-13T05:00:00Z', created_at: now } })
    if (path === `/api/v1/test-plans/${planId}/submissions` && request.method() === 'POST') { status = 'submitted'; return route.fulfill({ status: 201, json: submission() }) }
    return route.fulfill({ status: 404, json: { error: { message: `未模拟 ${path}` } } })
  })

  await page.goto('/imports/new')
  await page.getByLabel('选择 EML 文件').setInputFiles({ name: 'plan.eml', mimeType: 'message/rfc822', buffer: Buffer.from('From: demo@example.test') })
  await page.getByRole('checkbox').check()
  await page.getByRole('button', { name: '导入并生成计划' }).click()
  await expect(page.getByRole('heading', { name: '通信回归测试计划' })).toBeVisible()

  await page.getByRole('button', { name: '保存并送审' }).click()
  await expect(page.getByRole('heading', { name: '规则校验与人工审核' })).toBeVisible()
  await page.getByLabel('审核人姓名').fill('王芳')
  await page.getByLabel('9 位工号').fill('001234567')
  await page.getByRole('button', { name: '批准计划' }).click()

  await expect(page.getByRole('heading', { name: '平台报文预览与提交' })).toBeVisible()
  await page.getByRole('button', { name: '生成预览' }).click()
  await expect(page.getByText('SHA-256')).toBeVisible()
  await page.getByLabel('操作者姓名').fill('王芳')
  await page.getByLabel('9 位工号').fill('001234567')
  await page.getByRole('button', { name: '确认并提交平台' }).click()
  await expect(page.getByText('平台提交成功。')).toBeVisible()
  await expect(page.getByText('PLAN-001')).toBeVisible()
})

test('窄屏导入页无横向阻断布局', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/imports/new')
  await expect(page.getByRole('heading', { name: '从一封邮件开始' })).toBeVisible()
  const hasOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
  expect(hasOverflow).toBe(false)
})
