import { useEffect, useState } from 'react'
import { Controller, useFieldArray, useForm, type Control, type UseFormRegister } from 'react-hook-form'
import { ChevronDown, Eye, Plus, Save, Trash2 } from 'lucide-react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'

import { ApiError, api } from '../api/client'
import type { EvidenceReference, Plan, PlanDetailContent, TestCaseContent, TestPlanContent } from '../api/types'
import { EvidenceDrawer } from '../components/EvidenceDrawer'
import { PlanTabs } from '../components/PlanTabs'
import { Card, ErrorMessage, Field, Loading, Notice, PageHeader, PrimaryButton, ProvenanceBadge, SecondaryButton, StatusBadge } from '../components/ui'
import { inputClass } from '../components/utils'

const domains = [
  { key: 'communication', name: '通信', code: 'COMM' },
  { key: 'stability', name: '稳定性', code: 'STAB' },
  { key: 'power', name: '功耗', code: 'PWR' },
]
const testTypes = [['functional', '功能测试'], ['regression', '回归测试'], ['smoke', '冒烟测试'], ['performance', '性能测试'], ['stability', '稳定性测试'], ['compatibility', '兼容性测试'], ['security', '安全测试']]
const stages = [['component', '组件测试'], ['integration', '集成测试'], ['system', '系统测试'], ['acceptance', '验收测试']]
const priorities = [['critical', '紧急'], ['high', '高'], ['medium', '中'], ['low', '低']]

function lines(value: string) {
  return value.split('\n').map((item) => item.trim()).filter(Boolean)
}

function ArrayTextarea({ control, name, label }: { control: Control<TestPlanContent>; name: 'requirement_ids' | 'risks' | 'dependencies' | 'open_questions'; label: string }) {
  return <Controller control={control} name={name} render={({ field }) => <Field label={label}><textarea className={`${inputClass} min-h-24`} value={field.value.join('\n')} onChange={(event) => field.onChange(lines(event.target.value))} /></Field>} />
}

function EvidenceLinks({ references, onOpen }: { references: EvidenceReference[]; onOpen: (id: string) => void }) {
  if (!references.length) return <span className="text-xs text-slate-400">无证据锚点</span>
  return <div className="flex flex-wrap gap-2">{references.map((reference, index) => <button type="button" key={`${reference.evidence_segment_id}-${index}`} onClick={() => onOpen(reference.evidence_segment_id)} className="inline-flex items-center gap-1 rounded-lg bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700 hover:bg-emerald-100"><Eye className="size-3" />证据 {index + 1}</button>)}</div>
}

function CaseEditor({ control, register, domainIndex, caseIndex, value, onRemove, onOpenEvidence }: { control: Control<TestPlanContent>; register: UseFormRegister<TestPlanContent>; domainIndex: number; caseIndex: number; value: TestCaseContent; onRemove: () => void; onOpenEvidence: (id: string) => void }) {
  const steps = useFieldArray({ control, name: `details.${domainIndex}.test_cases.${caseIndex}.steps` })
  return (
    <details className="rounded-xl border border-slate-200 bg-white" open={caseIndex === 0}>
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 p-4">
        <span className="min-w-0 truncate text-sm font-semibold">用例 {caseIndex + 1} · {value.title || '未命名'}</span>
        <ChevronDown className="size-4 shrink-0 text-slate-400" />
      </summary>
      <div className="space-y-4 border-t border-slate-100 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3"><ProvenanceBadge value={value.provenance} /><EvidenceLinks references={value.evidence_references} onOpen={onOpenEvidence} /></div>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="用例标题"><input className={inputClass} {...register(`details.${domainIndex}.test_cases.${caseIndex}.title`)} /></Field>
          <Field label="优先级"><select className={inputClass} {...register(`details.${domainIndex}.test_cases.${caseIndex}.priority`)}><option value="">请选择</option>{priorities.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></Field>
          <Field label="测试目标"><textarea className={`${inputClass} min-h-24`} {...register(`details.${domainIndex}.test_cases.${caseIndex}.objective`)} /></Field>
          <Controller control={control} name={`details.${domainIndex}.test_cases.${caseIndex}.preconditions`} render={({ field }) => <Field label="前置条件" hint="每行一项"><textarea className={`${inputClass} min-h-24`} value={field.value.join('\n')} onChange={(event) => field.onChange(lines(event.target.value))} /></Field>} />
          <Field label="测试数据"><textarea className={`${inputClass} min-h-24`} {...register(`details.${domainIndex}.test_cases.${caseIndex}.test_data`)} /></Field>
          <Field label="预期结果"><textarea className={`${inputClass} min-h-24`} {...register(`details.${domainIndex}.test_cases.${caseIndex}.expected_result`)} /></Field>
          <Controller control={control} name={`details.${domainIndex}.test_cases.${caseIndex}.open_questions`} render={({ field }) => <Field label="用例待确认事项" hint="处理后删除对应行"><textarea className={`${inputClass} min-h-24`} value={field.value.join('\n')} onChange={(event) => field.onChange(lines(event.target.value))} /></Field>} />
        </div>
        <div>
          <div className="flex items-center justify-between"><h4 className="text-sm font-semibold">执行步骤</h4><SecondaryButton type="button" onClick={() => steps.append({ step_number: steps.fields.length + 1, action: '' })}><Plus className="size-4" />添加步骤</SecondaryButton></div>
          <div className="mt-3 space-y-2">{steps.fields.map((step, stepIndex) => <div className="flex items-center gap-2" key={step.id}><span className="w-7 text-center text-sm text-slate-400">{stepIndex + 1}</span><input type="hidden" value={stepIndex + 1} {...register(`details.${domainIndex}.test_cases.${caseIndex}.steps.${stepIndex}.step_number`, { valueAsNumber: true })} /><input className={inputClass} aria-label={`步骤 ${stepIndex + 1}`} {...register(`details.${domainIndex}.test_cases.${caseIndex}.steps.${stepIndex}.action`)} /><button type="button" disabled={steps.fields.length === 1} className="rounded-lg p-2 text-slate-400 hover:bg-rose-50 hover:text-rose-600 disabled:cursor-not-allowed disabled:opacity-30" onClick={() => steps.remove(stepIndex)} aria-label={`删除步骤 ${stepIndex + 1}`}><Trash2 className="size-4" /></button></div>)}</div>
        </div>
        <div className="flex justify-end"><SecondaryButton type="button" className="text-rose-600" onClick={onRemove}><Trash2 className="size-4" />删除用例</SecondaryButton></div>
      </div>
    </details>
  )
}

function DomainEditor({ control, register, index, value, onRemove, onOpenEvidence }: { control: Control<TestPlanContent>; register: UseFormRegister<TestPlanContent>; index: number; value: PlanDetailContent; onRemove: () => void; onOpenEvidence: (id: string) => void }) {
  const requirements = useFieldArray({ control, name: `details.${index}.requirements` })
  const cases = useFieldArray({ control, name: `details.${index}.test_cases` })
  const fallbackEvidence = value.evidence_references
  function addCase() {
    const evidence = fallbackEvidence.length ? fallbackEvidence : value.requirements.flatMap((item) => item.evidence_references).slice(0, 1)
    cases.append({ title: '', objective: '', preconditions: [], steps: [{ step_number: 1, action: '' }], test_data: '', expected_result: '', priority: 'medium', domain_key: value.domain_key, evidence_references: evidence, provenance: 'user_provided', open_questions: [] })
  }
  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-slate-50 px-5 py-4"><div><p className="text-xs font-semibold text-brand">测试领域 {index + 1}</p><h2 className="mt-1 text-lg font-semibold">{value.domain_name || '待选择领域'}</h2></div><SecondaryButton type="button" className="text-rose-600" onClick={onRemove}><Trash2 className="size-4" />删除领域</SecondaryButton></div>
      <div className="space-y-7 p-5 sm:p-6">
        {value.unresolved_fields.length > 0 && <Notice tone="warning">待确认字段：{value.unresolved_fields.join('、')}。填写并保存后，服务端会重新计算来源状态。</Notice>}
        <div className="grid gap-4 md:grid-cols-3">
          <Field label="领域"><select className={inputClass} {...register(`details.${index}.domain_key`)}><option value="">请选择</option>{domains.map((item) => <option key={item.key} value={item.key}>{item.name}</option>)}</select></Field>
          <Field label="负责人"><input className={inputClass} {...register(`details.${index}.owner_name`)} /></Field>
          <Field label="负责人工号"><input className={inputClass} inputMode="numeric" maxLength={9} {...register(`details.${index}.owner_employee_id`)} /></Field>
          <Field label="开始日期"><input className={inputClass} type="date" {...register(`details.${index}.execution_start_date`, { setValueAs: (value: string) => value || null })} /></Field>
          <Field label="结束日期"><input className={inputClass} type="date" {...register(`details.${index}.execution_end_date`, { setValueAs: (value: string) => value || null })} /></Field>
          <Field label="领域范围"><input className={inputClass} {...register(`details.${index}.scope`)} /></Field>
        </div>
        <Controller control={control} name={`details.${index}.unresolved_fields`} render={({ field }) => <Field label="领域待确认字段" hint="补齐后删除对应行"><textarea className={`${inputClass} min-h-20`} value={field.value.join('\n')} onChange={(event) => field.onChange(lines(event.target.value))} /></Field>} />
        <div><div className="flex items-center justify-between"><h3 className="font-semibold">需求</h3><SecondaryButton type="button" onClick={() => requirements.append({ text: '', evidence_references: fallbackEvidence.slice(0, 1), provenance: 'user_provided' })}><Plus className="size-4" />添加需求</SecondaryButton></div><div className="mt-3 space-y-3">{requirements.fields.map((requirement, requirementIndex) => <div key={requirement.id} className="flex items-start gap-2"><div className="min-w-0 flex-1"><input className={inputClass} aria-label={`需求 ${requirementIndex + 1}`} {...register(`details.${index}.requirements.${requirementIndex}.text`)} /><div className="mt-2 flex items-center justify-between"><ProvenanceBadge value={requirement.provenance} /><EvidenceLinks references={requirement.evidence_references} onOpen={onOpenEvidence} /></div></div><button type="button" className="rounded-lg p-2 text-slate-400 hover:bg-rose-50 hover:text-rose-600" onClick={() => requirements.remove(requirementIndex)} aria-label={`删除需求 ${requirementIndex + 1}`}><Trash2 className="size-4" /></button></div>)}</div></div>
        <div><div className="flex items-center justify-between"><h3 className="font-semibold">测试用例</h3><SecondaryButton type="button" onClick={addCase}><Plus className="size-4" />添加用例</SecondaryButton></div><div className="mt-3 space-y-3">{cases.fields.map((testCase, caseIndex) => <CaseEditor key={testCase.id} control={control} register={register} domainIndex={index} caseIndex={caseIndex} value={testCase} onRemove={() => cases.remove(caseIndex)} onOpenEvidence={onOpenEvidence} />)}</div></div>
      </div>
    </Card>
  )
}

function newDomain(reference: EvidenceReference | undefined): PlanDetailContent {
  return { domain_key: 'communication', domain_name: '通信', domain_code: 'COMM', owner_name: '', owner_employee_id: '', execution_start_date: null, execution_end_date: null, scope: '', requirements: [], test_cases: [], evidence_references: reference ? [reference] : [], unresolved_fields: [], field_metadata: {} }
}

export function PlanEditPage() {
  const { planId = '' } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const [plan, setPlan] = useState<Plan | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [message, setMessage] = useState<string | null>((location.state as { message?: string } | null)?.message ?? null)
  const [evidenceId, setEvidenceId] = useState<string | null>(null)
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const form = useForm<TestPlanContent>({ defaultValues: undefined })
  const details = useFieldArray({ control: form.control, name: 'details' })

  useEffect(() => { void api.getPlan(planId).then((result) => { setPlan(result); form.reset(result.version.content) }).catch(setError) }, [form, planId])

  async function save(content: TestPlanContent) {
    if (!plan) return null
    setBusyAction('save'); setError(null); setMessage(null)
    try {
      content.details.forEach((detail) => {
        const selected = domains.find((item) => item.key === detail.domain_key)
        if (selected) { detail.domain_name = selected.name; detail.domain_code = selected.code }
        detail.test_cases.forEach((testCase) => { testCase.domain_key = detail.domain_key })
      })
      const result = await api.savePlan(plan.id, plan.current_version, content)
      const refreshed = await api.getPlan(plan.id)
      setPlan(refreshed); form.reset(refreshed.version.content)
      setMessage(result.created ? `已保存为版本 ${result.version.version_number}` : '内容没有变化，未创建新版本。')
      return refreshed
    } catch (caught) {
      setError(caught)
      if (caught instanceof ApiError && caught.status === 409) setMessage('计划已被其他操作更新，请刷新后重新编辑。')
      return null
    } finally { setBusyAction(null) }
  }

  async function validateOrReview(content: TestPlanContent, submit: boolean) {
    const saved = await save(content)
    if (!saved) return
    setBusyAction(submit ? 'review' : 'validate'); setError(null)
    try {
      const validation = submit ? await api.submitForReview(saved.id) : await api.validatePlan(saved.id)
      if (submit) navigate(`/plans/${saved.id}/review`, { state: { validation } })
      else navigate(`/plans/${saved.id}/review`, { state: { validation, validationOnly: true } })
    } catch (caught) { setError(caught) } finally { setBusyAction(null) }
  }

  if (error && !plan) return <ErrorMessage error={error} />
  if (!plan) return <Loading label="正在读取计划草稿" />
  const locked = ['pending_review', 'submitting', 'submitted', 'unknown'].includes(plan.status)
  return (
    <div>
      <PageHeader eyebrow={`版本 ${plan.current_version}`} title={plan.version.content.plan_name || '未命名测试计划'} description="编辑完整计划快照。保存会创建不可变版本，来源与规则由服务端重新计算。" actions={<StatusBadge status={plan.status} />} />
      <div className="mt-6"><PlanTabs planId={plan.id} /></div>
      {(location.state as { warnings?: string[] } | null)?.warnings?.length ? <div className="mt-5"><Notice tone="warning">导入提示：{(location.state as { warnings: string[] }).warnings.join('、')}</Notice></div> : null}
      {message && <div className="mt-5"><Notice tone={message.includes('冲突') ? 'warning' : 'success'}>{message}</Notice></div>}
      {error ? <div className="mt-5"><ErrorMessage error={error} /></div> : null}
      {plan.version.content.open_questions.length > 0 && <div className="mt-5"><Notice tone="warning"><strong>空白或待确认草稿：</strong>{plan.version.content.open_questions.join('；')}</Notice></div>}
      <form className="mt-6 space-y-6" onSubmit={form.handleSubmit((content) => void save(content))}>
        <fieldset disabled={locked} className="space-y-6">
          <Card className="p-5 sm:p-6"><h2 className="text-lg font-semibold">计划概况</h2><div className="mt-5 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            <Field label="计划名称"><input className={inputClass} {...form.register('plan_name')} /></Field><Field label="项目名称"><input className={inputClass} {...form.register('project_name')} /></Field><Field label="项目编码"><input className={inputClass} {...form.register('project_code')} /></Field>
            <Field label="测试类型"><select className={inputClass} {...form.register('test_type')}><option value="">请选择</option>{testTypes.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></Field><Field label="测试阶段"><select className={inputClass} {...form.register('test_stage')}><option value="">请选择</option>{stages.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></Field><Field label="优先级"><select className={inputClass} {...form.register('priority')}><option value="">请选择</option>{priorities.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></Field>
            <Field label="测试轮次"><input className={inputClass} {...form.register('test_round')} /></Field><Field label="测试版本"><input className={inputClass} {...form.register('test_version')} /></Field><ArrayTextarea control={form.control} name="requirement_ids" label="需求编号" />
            <Field label="计划开始日期"><input className={inputClass} type="date" {...form.register('planned_start_date', { setValueAs: (value: string) => value || null })} /></Field><Field label="计划结束日期"><input className={inputClass} type="date" {...form.register('planned_end_date', { setValueAs: (value: string) => value || null })} /></Field>
          </div><div className="mt-4 grid gap-4 md:grid-cols-2"><Field label="测试目标"><textarea className={`${inputClass} min-h-28`} {...form.register('objective')} /></Field><Field label="测试范围"><textarea className={`${inputClass} min-h-28`} {...form.register('scope')} /></Field><Field label="测试环境"><textarea className={`${inputClass} min-h-24`} {...form.register('environment')} /></Field><Field label="备注"><textarea className={`${inputClass} min-h-24`} {...form.register('notes')} /></Field><ArrayTextarea control={form.control} name="risks" label="风险（每行一项）" /><ArrayTextarea control={form.control} name="dependencies" label="依赖（每行一项）" /><ArrayTextarea control={form.control} name="open_questions" label="计划待确认事项（处理后删除对应行）" /></div></Card>
          <div className="flex items-center justify-between"><div><h2 className="text-xl font-semibold">领域与用例</h2><p className="mt-1 text-sm text-slate-500">最多 10 个领域、每个领域 20 条用例。</p></div><SecondaryButton type="button" onClick={() => details.append(newDomain(plan.version.content.evidence_references[0]))}><Plus className="size-4" />添加领域</SecondaryButton></div>
          {details.fields.map((detail, index) => <DomainEditor key={detail.id} control={form.control} register={form.register} index={index} value={detail} onRemove={() => details.remove(index)} onOpenEvidence={setEvidenceId} />)}
        </fieldset>
        <div className="sticky bottom-4 z-30 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white/95 p-3 shadow-soft backdrop-blur"><Link className="px-3 text-sm font-medium text-slate-500 hover:text-ink" to="/plans">返回列表</Link><div className="flex flex-wrap gap-2"><SecondaryButton type="button" disabled={locked || !!busyAction} onClick={form.handleSubmit((content) => void validateOrReview(content, false))}>校验计划</SecondaryButton><SecondaryButton type="submit" disabled={locked || !!busyAction}><Save className="size-4" />{busyAction === 'save' ? '保存中…' : '保存版本'}</SecondaryButton><PrimaryButton type="button" disabled={locked || !!busyAction} onClick={form.handleSubmit((content) => void validateOrReview(content, true))}>{busyAction === 'review' ? '送审中…' : '保存并送审'}</PrimaryButton></div></div>
      </form>
      <EvidenceDrawer evidenceId={evidenceId} onClose={() => setEvidenceId(null)} />
    </div>
  )
}
