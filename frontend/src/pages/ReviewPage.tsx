import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Check, CheckCircle2, Info, RotateCcw, ShieldAlert } from 'lucide-react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'

import { api } from '../api/client'
import type { Plan, ReviewRecord, ValidationIssue, ValidationResult } from '../api/types'
import { PlanTabs } from '../components/PlanTabs'
import { Card, ErrorMessage, Field, Loading, Notice, PageHeader, PrimaryButton, SecondaryButton, StatusBadge } from '../components/ui'
import { formatDateTime, inputClass } from '../components/utils'

const severity = {
  blocking: { label: '阻断', style: 'border-rose-200 bg-rose-50', icon: ShieldAlert, iconStyle: 'text-rose-600' },
  warning: { label: '警告', style: 'border-amber-200 bg-amber-50', icon: AlertTriangle, iconStyle: 'text-amber-600' },
  info: { label: '提示', style: 'border-blue-200 bg-blue-50', icon: Info, iconStyle: 'text-blue-600' },
}

function RuleIssue({ issue, checked, onCheck }: { issue: ValidationIssue; checked: boolean; onCheck: (value: boolean) => void }) {
  const meta = severity[issue.severity]
  const Icon = meta.icon
  return (
    <div className={`rounded-xl border p-4 ${meta.style}`}>
      <div className="flex items-start gap-3">
        <Icon className={`mt-0.5 size-5 shrink-0 ${meta.iconStyle}`} aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2"><span className="text-xs font-semibold">{meta.label}</span><code className="break-all text-xs text-slate-500">{issue.rule_id} · {issue.field_path || '全局'}</code></div>
          <p className="mt-2 text-sm font-medium text-slate-800">{issue.message}</p>
          {issue.suggestion && <p className="mt-1 text-sm text-slate-600">建议：{issue.suggestion}</p>}
          {issue.severity === 'warning' && <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm font-medium"><input type="checkbox" checked={checked} onChange={(event) => onCheck(event.target.checked)} className="size-4 rounded border-slate-300 text-brand" />我已核对并接受此警告</label>}
        </div>
      </div>
    </div>
  )
}

export function ReviewPage() {
  const { planId = '' } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const initialValidation = (location.state as { validation?: ValidationResult } | null)?.validation ?? null
  const [plan, setPlan] = useState<Plan | null>(null)
  const [validation, setValidation] = useState<ValidationResult | null>(initialValidation)
  const [reviews, setReviews] = useState<ReviewRecord[]>([])
  const [acknowledged, setAcknowledged] = useState<string[]>([])
  const [operatorName, setOperatorName] = useState('')
  const [employeeId, setEmployeeId] = useState('')
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    void Promise.all([api.getPlan(planId), api.listReviews(planId)]).then(async ([loadedPlan, loadedReviews]) => {
      setPlan(loadedPlan); setReviews(loadedReviews)
      if (!initialValidation && loadedPlan.status !== 'submitted') {
        try { setValidation(await api.validatePlan(planId)) } catch (caught) { setError(caught) }
      }
    }).catch(setError)
  }, [initialValidation, planId])

  const warningIds = useMemo(() => validation?.issues.filter((item) => item.severity === 'warning').map((item) => item.id) ?? [], [validation])
  const canApprove = plan?.status === 'pending_review' && validation?.blocking_count === 0 && warningIds.every((id) => acknowledged.includes(id)) && operatorName.trim() && /^\d{9}$/.test(employeeId)

  async function sendForReview() {
    setBusy('submit'); setError(null)
    try { const result = await api.submitForReview(planId); setValidation(result); setPlan(await api.getPlan(planId)); setMessage('计划已进入待审核状态。') } catch (caught) { setError(caught) } finally { setBusy(null) }
  }

  async function decide(decision: 'approved' | 'revision_requested') {
    setBusy(decision); setError(null)
    try {
      await api.reviewPlan(planId, { decision, operator_name: operatorName, operator_employee_id: employeeId, comment: comment.trim() || null, validation_run_id: validation?.id ?? null, acknowledged_warning_ids: decision === 'approved' ? acknowledged : [] })
      if (decision === 'approved') navigate(`/plans/${planId}/submit`, { state: { message: '计划已批准，可以生成平台报文预览。' } })
      else navigate(`/plans/${planId}/edit`, { state: { message: '计划已退回，请按审核意见修改后重新送审。' } })
    } catch (caught) { setError(caught) } finally { setBusy(null) }
  }

  if (error && !plan) return <ErrorMessage error={error} />
  if (!plan) return <Loading label="正在读取审核信息" />
  return (
    <div>
      <PageHeader eyebrow={`版本 ${plan.current_version}`} title="规则校验与人工审核" description={plan.version.content.plan_name || '未命名测试计划'} actions={<StatusBadge status={plan.status} />} />
      <div className="mt-6"><PlanTabs planId={plan.id} /></div>
      {message && <div className="mt-5"><Notice tone="success">{message}</Notice></div>}
      {error ? <div className="mt-5"><ErrorMessage error={error} /></div> : null}
      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <Card className="p-5 sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-lg font-semibold">确定性规则</h2><p className="mt-1 text-sm text-slate-500">规则集 {validation?.rule_set_version ?? '—'}</p></div>{validation && <div className="flex gap-2"><span className="rounded-lg bg-rose-50 px-2.5 py-1 text-xs font-semibold text-rose-700">{validation.blocking_count} 阻断</span><span className="rounded-lg bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-800">{validation.warning_count} 警告</span></div>}</div>
          {!validation ? <Loading label="正在执行校验" /> : validation.issues.length === 0 ? <div className="mt-6 flex items-center gap-3 rounded-xl bg-emerald-50 p-5 text-sm font-medium text-emerald-700"><CheckCircle2 className="size-5" />全部规则通过</div> : <div className="mt-5 space-y-3">{validation.issues.map((issue) => <RuleIssue key={issue.id} issue={issue} checked={acknowledged.includes(issue.id)} onCheck={(checked) => setAcknowledged((current) => checked ? [...current, issue.id] : current.filter((id) => id !== issue.id))} />)}</div>}
        </Card>
        <div className="space-y-6">
          <Card className="p-5 sm:p-6"><h2 className="text-lg font-semibold">审核声明</h2><p className="mt-2 text-sm leading-6 text-slate-500">审核绑定当前版本、内容哈希和警告确认。修改计划后，本次批准自动失效。</p>
            {plan.status === 'draft' || plan.status === 'revision_requested' ? <div className="mt-5"><Notice tone="warning">计划尚未送审。规则无阻断时可进入待审核状态。</Notice><PrimaryButton className="mt-4 w-full" disabled={!!busy || !!validation?.blocking_count} onClick={() => void sendForReview()}>{busy === 'submit' ? '送审中…' : '提交审核'}</PrimaryButton></div> : plan.status === 'pending_review' ? <div className="mt-5 space-y-4"><Field label="审核人姓名"><input className={inputClass} value={operatorName} onChange={(event) => setOperatorName(event.target.value)} /></Field><Field label="9 位工号"><input className={inputClass} inputMode="numeric" maxLength={9} value={employeeId} onChange={(event) => setEmployeeId(event.target.value)} /></Field><Field label="审核意见" hint="退回时必填"><textarea className={`${inputClass} min-h-24`} value={comment} onChange={(event) => setComment(event.target.value)} /></Field><div className="grid grid-cols-2 gap-2"><SecondaryButton className="text-amber-700" disabled={!!busy || !operatorName.trim() || !/^\d{9}$/.test(employeeId) || !comment.trim()} onClick={() => void decide('revision_requested')}><RotateCcw className="size-4" />退回修改</SecondaryButton><PrimaryButton disabled={!!busy || !canApprove} onClick={() => void decide('approved')}><Check className="size-4" />批准计划</PrimaryButton></div></div> : <div className="mt-5"><Notice tone={plan.status === 'approved' || plan.status === 'submitted' ? 'success' : 'info'}>当前状态无需新的审核操作。</Notice></div>}
          </Card>
          <Card className="p-5 sm:p-6"><h2 className="font-semibold">审核历史</h2>{reviews.length === 0 ? <p className="mt-3 text-sm text-slate-500">暂无审核记录</p> : <ol className="mt-4 space-y-4">{reviews.map((review) => <li key={review.id} className="border-l-2 border-slate-200 pl-4"><div className="flex items-center justify-between gap-2"><span className="text-sm font-semibold">{review.decision === 'approved' ? '批准' : '退回修改'}</span><span className="text-xs text-slate-400">{formatDateTime(review.created_at)}</span></div><p className="mt-1 text-xs text-slate-500">{review.operator_name} · {review.operator_employee_id}</p>{review.comment && <p className="mt-2 text-sm text-slate-600">{review.comment}</p>}</li>)}</ol>}</Card>
          <Link className="block text-center text-sm font-semibold text-brand" to={`/plans/${planId}/edit`}>返回计划编辑</Link>
        </div>
      </div>
    </div>
  )
}
