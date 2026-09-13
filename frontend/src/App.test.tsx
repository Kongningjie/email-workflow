import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'

const planId = '11111111-1111-4111-8111-111111111111'
const versionId = '22222222-2222-4222-8222-222222222222'
const now = '2026-09-13T04:00:00Z'

const content = {
  plan_name: '通信回归测试计划', project_name: 'Atlas', project_code: 'ATLAS', requirement_ids: ['REQ-101'],
  test_type: 'functional', test_stage: 'system', test_round: '第一轮', priority: 'high', test_version: '1.0',
  planned_start_date: '2026-09-15', planned_end_date: '2026-09-20', objective: '验证通信主链路', scope: '通信功能',
  environment: '测试环境 A', risks: ['网络抖动'], dependencies: ['测试 SIM 卡'], notes: '', open_questions: [], evidence_references: [], field_metadata: {},
  details: [{
    domain_key: 'communication', domain_name: '通信', domain_code: 'COMM', owner_name: '王芳', owner_employee_id: '001234567',
    execution_start_date: '2026-09-15', execution_end_date: '2026-09-20', scope: '入网与重连', unresolved_fields: [], evidence_references: [], field_metadata: {},
    requirements: [{ text: '设备断网后自动重连', provenance: 'source', evidence_references: [] }],
    test_cases: [{ title: '断网后自动重连', objective: '验证设备恢复网络', preconditions: ['设备已入网'], steps: [{ step_number: 1, action: '断开并恢复网络' }], test_data: '', expected_result: '设备自动重连', priority: 'high', domain_key: 'communication', evidence_references: [], provenance: 'model_suggestion', open_questions: [] }],
  }],
}

function plan(status = 'draft') {
  return { id: planId, source_email_id: '33333333-3333-4333-8333-333333333333', current_version: 1, status, external_platform_id: null, created_at: now, updated_at: now, version: { id: versionId, test_plan_id: planId, version_number: 1, content, content_sha256: 'a'.repeat(64), domain_catalog_version: '1.0.0', value_catalog_version: '1.0.0', prompt_version: '1.0.0', prompt_sha256: 'b'.repeat(64), created_at: now } }
}

function response(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
}

function renderAt(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>)
}

afterEach(() => vi.unstubAllGlobals())

describe('阶段 5 前端闭环', () => {
  it('导入页只在选择 EML 并确认外部处理后允许提交', async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      void url
      void init
      return response({ test_plan_id: planId, deduplicated: false, warnings: [] })
    })
    vi.stubGlobal('fetch', fetchMock)
    renderAt('/imports/new')

    const submit = screen.getByRole('button', { name: '导入并生成计划' })
    expect(submit).toBeDisabled()
    fireEvent.change(screen.getByLabelText('选择 EML 文件'), { target: { files: [new File(['mail'], 'plan.eml', { type: 'message/rfc822' })] } })
    fireEvent.click(screen.getByRole('checkbox'))
    expect(submit).toBeEnabled()
    fireEvent.click(submit)

    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const [, init] = fetchMock.mock.calls[0]
    expect(init?.body).toBeInstanceOf(FormData)
  })

  it('计划列表展示真实名称、版本和语义状态', async () => {
    const fetchMock = vi.fn((url: string) => url.endsWith('/test-plans') ? response([{ ...plan('approved'), version: undefined }]) : response(plan('approved')))
    vi.stubGlobal('fetch', fetchMock)
    renderAt('/plans')

    expect(await screen.findByText('通信回归测试计划')).toBeInTheDocument()
    expect(screen.getByText('已批准')).toBeInTheDocument()
    expect(screen.getByText(/版本 1/)).toBeInTheDocument()
  })

  it('嵌套编辑页展示领域、用例与固定操作栏', async () => {
    vi.stubGlobal('fetch', vi.fn(() => response(plan('draft'))))
    renderAt(`/plans/${planId}/edit`)

    expect(await screen.findByRole('heading', { name: '通信回归测试计划' })).toBeInTheDocument()
    expect(screen.getByText('领域与用例')).toBeInTheDocument()
    expect(screen.getByText(/用例 1 · 断网后自动重连/)).toBeInTheDocument()
    expect(screen.getByText('模型建议')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '保存版本' })).toBeEnabled()
  })

  it('保存遇到版本冲突时提示刷新而不覆盖服务端内容', async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url.endsWith('/versions') && init?.method === 'POST') {
        return response({ error: { code: 'base_version_conflict', message: '计划已被其他操作更新，请刷新后重试' } }, 409)
      }
      return response(plan('draft'))
    })
    vi.stubGlobal('fetch', fetchMock)
    renderAt(`/plans/${planId}/edit`)

    fireEvent.click(await screen.findByRole('button', { name: '保存版本' }))
    expect(await screen.findByText('计划已被其他操作更新，请刷新后重新编辑。')).toBeInTheDocument()
  })

  it('审核页要求逐条确认 Warning 和 9 位工号', async () => {
    const validation = { id: '44444444-4444-4444-8444-444444444444', test_plan_id: planId, test_plan_version_id: versionId, content_sha256: 'a'.repeat(64), rule_set_version: '1.0.0', status: 'passed', blocking_count: 0, warning_count: 1, finished_at: now, issues: [{ id: '55555555-5555-4555-8555-555555555555', rule_id: 'plan.context_missing', rule_version: '1.0', severity: 'warning', field_path: 'risks', message: '建议补充风险', suggestion: '核对测试上下文' }] }
    const fetchMock = vi.fn((url: string) => url.endsWith('/reviews') ? response([]) : response(plan('pending_review')))
    vi.stubGlobal('fetch', fetchMock)
    render(<MemoryRouter initialEntries={[{ pathname: `/plans/${planId}/review`, state: { validation } }]}><App /></MemoryRouter>)

    const approve = await screen.findByRole('button', { name: '批准计划' })
    expect(approve).toBeDisabled()
    fireEvent.change(screen.getByLabelText('审核人姓名'), { target: { value: '王芳' } })
    fireEvent.change(screen.getByLabelText('9 位工号'), { target: { value: '001234567' } })
    fireEvent.click(screen.getByRole('checkbox', { name: '我已核对并接受此警告' }))
    expect(approve).toBeEnabled()
  })

  it('未知提交先提供对账，明确未找到后才显示重试', async () => {
    const submission = { id: '66666666-6666-4666-8666-666666666666', test_plan_id: planId, test_plan_version_id: versionId, payload_preview_id: '77777777-7777-4777-8777-777777777777', mapping_profile_version: '1.0.0', payload_sha256: 'c'.repeat(64), submission_request_id: '88888888-8888-4888-8888-888888888888', idempotency_key: 'd'.repeat(64), status: 'unknown', operator_name: '王芳', operator_employee_id: '001234567', confirmed_at: now, external_request_id: null, external_plan_id: null, safe_response_summary: '平台未找到请求', finished_at: null, created_at: now }
    const fetchMock = vi.fn((url: string) => url.endsWith('/submissions') ? response([submission]) : response(plan('unknown')))
    vi.stubGlobal('fetch', fetchMock)
    renderAt(`/plans/${planId}/submit`)

    expect(await screen.findByRole('button', { name: '查询平台结果' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '原参数重试' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '生成预览' })).not.toBeInTheDocument()
  })
})
