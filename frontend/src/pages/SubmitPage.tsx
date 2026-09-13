import { useEffect, useState } from 'react'
import { CheckCircle2, Clock3, Copy, RefreshCw, RotateCw, Send, ShieldCheck } from 'lucide-react'
import { useLocation, useParams } from 'react-router-dom'

import { api } from '../api/client'
import type { PayloadPreview, Plan, Submission } from '../api/types'
import { PlanTabs } from '../components/PlanTabs'
import { Card, ErrorMessage, Field, Loading, Notice, PageHeader, PrimaryButton, SecondaryButton, StatusBadge } from '../components/ui'
import { formatDateTime, inputClass } from '../components/utils'

function SubmissionCard({ submission, busy, onReconcile, onRetry }: { submission: Submission; busy: boolean; onReconcile: () => void; onRetry: () => void }) {
  const canRetry = submission.status === 'unknown' && submission.safe_response_summary?.includes('未找到')
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-xs text-slate-400">{formatDateTime(submission.created_at)}</p><p className="mt-1 font-semibold">请求 {submission.submission_request_id.slice(0, 8)}</p></div><StatusBadge status={submission.status} /></div>
      {submission.safe_response_summary && <p className="mt-4 rounded-lg bg-slate-50 p-3 text-sm text-slate-600">{submission.safe_response_summary}</p>}
      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2"><div><dt className="text-slate-400">操作者</dt><dd className="mt-1 text-slate-700">{submission.operator_name} · {submission.operator_employee_id}</dd></div><div><dt className="text-slate-400">外部计划 ID</dt><dd className="mt-1 break-all text-slate-700">{submission.external_plan_id || '—'}</dd></div></dl>
      {submission.status === 'unknown' && <div className="mt-4 flex gap-2"><PrimaryButton disabled={busy} onClick={onReconcile}><RefreshCw className="size-4" />查询平台结果</PrimaryButton>{canRetry && <SecondaryButton disabled={busy} onClick={onRetry}><RotateCw className="size-4" />原参数重试</SecondaryButton>}</div>}
    </Card>
  )
}

export function SubmitPage() {
  const { planId = '' } = useParams()
  const location = useLocation()
  const [plan, setPlan] = useState<Plan | null>(null)
  const [preview, setPreview] = useState<PayloadPreview | null>(null)
  const [submissions, setSubmissions] = useState<Submission[]>([])
  const [operatorName, setOperatorName] = useState('')
  const [employeeId, setEmployeeId] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [message, setMessage] = useState<string | null>((location.state as { message?: string } | null)?.message ?? null)

  async function refresh() {
    const [loadedPlan, loadedSubmissions] = await Promise.all([api.getPlan(planId), api.listSubmissions(planId)])
    setPlan(loadedPlan); setSubmissions(loadedSubmissions)
  }
  useEffect(() => {
    void Promise.all([api.getPlan(planId), api.listSubmissions(planId)])
      .then(([loadedPlan, loadedSubmissions]) => {
        setPlan(loadedPlan)
        setSubmissions(loadedSubmissions)
      })
      .catch(setError)
  }, [planId])

  async function createPreview() {
    setBusy('preview'); setError(null); setMessage(null)
    try { setPreview(await api.createPreview(planId)); setMessage('预览已生成，请核对报文和哈希后确认提交。') } catch (caught) { setError(caught) } finally { setBusy(null) }
  }
  async function confirm() {
    if (!preview) return
    setBusy('confirm'); setError(null)
    try {
      const result = await api.confirmSubmission(planId, { confirmation_token: preview.confirmation_token, payload_sha256: preview.payload_sha256, operator_name: operatorName, operator_employee_id: employeeId })
      setPreview(null); setMessage(result.status === 'submitted' ? '平台提交成功。' : result.status === 'unknown' ? '平台结果未知，请先对账，不要重复创建计划。' : '平台明确拒绝，请修改业务字段并重新审核。'); await refresh()
    } catch (caught) { setError(caught) } finally { setBusy(null) }
  }
  async function act(id: string, action: 'reconcile' | 'retry') {
    setBusy(id); setError(null)
    try { const result = action === 'reconcile' ? await api.reconcileSubmission(id) : await api.retrySubmission(id); setMessage(result.safe_response_summary ?? '操作完成'); await refresh() } catch (caught) { setError(caught) } finally { setBusy(null) }
  }

  if (error && !plan) return <ErrorMessage error={error} />
  if (!plan) return <Loading label="正在读取提交状态" />
  return (
    <div>
      <PageHeader eyebrow={`版本 ${plan.current_version}`} title="平台报文预览与提交" description={plan.version.content.plan_name || '未命名测试计划'} actions={<StatusBadge status={plan.status} />} />
      <div className="mt-6"><PlanTabs planId={plan.id} /></div>
      {message && <div className="mt-5"><Notice tone={message.includes('未知') || message.includes('拒绝') ? 'warning' : 'success'}>{message}</Notice></div>}
      {error ? <div className="mt-5"><ErrorMessage error={error} /></div> : null}
      {plan.status !== 'approved' && !preview && <div className="mt-6"><Notice tone={plan.status === 'submitted' ? 'success' : 'warning'}>{plan.status === 'submitted' ? '该计划已成功提交，记录不可修改。' : plan.status === 'unknown' ? '上次提交结果未知，请在下方执行对账。' : plan.status === 'submission_failed' ? '平台明确拒绝。请返回编辑页面修正业务字段，重新送审和确认。' : '只有当前已批准版本可以生成平台报文预览。'}</Notice></div>}
      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <Card className="overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4"><div><h2 className="font-semibold">平台报文</h2><p className="mt-1 text-xs text-slate-500">只包含平台契约字段，不包含邮件正文、证据或审核意见。</p></div>{plan.status === 'approved' && <PrimaryButton disabled={!!busy} onClick={() => void createPreview()}><Send className="size-4" />{busy === 'preview' ? '生成中…' : preview ? '重新生成预览' : '生成预览'}</PrimaryButton>}</div>
          {!preview ? <div className="flex min-h-80 flex-col items-center justify-center p-8 text-center text-slate-400"><ShieldCheck className="size-10" /><p className="mt-3 text-sm">生成预览后在此核对规范化报文</p></div> : <div className="p-5"><div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-slate-50 p-4"><div className="min-w-0"><p className="text-xs text-slate-400">SHA-256</p><code className="mt-1 block truncate text-xs text-slate-700">{preview.payload_sha256}</code></div><SecondaryButton onClick={() => void navigator.clipboard?.writeText(preview.payload_sha256)}><Copy className="size-4" />复制哈希</SecondaryButton></div><div className="mt-3 flex items-center gap-2 text-xs text-slate-500"><Clock3 className="size-4" />确认令牌有效至 {formatDateTime(preview.expires_at)}</div><pre className="mt-4 max-h-[620px] overflow-auto whitespace-pre-wrap break-words rounded-xl bg-slate-950 p-5 text-xs leading-6 text-slate-200">{JSON.stringify(preview.payload, null, 2)}</pre></div>}
        </Card>
        <div className="space-y-6">
          <Card className="p-5 sm:p-6"><h2 className="font-semibold">二次确认</h2><p className="mt-2 text-sm leading-6 text-slate-500">服务端会重新生成报文并核对版本、批准记录与哈希。</p><div className="mt-5 space-y-4"><Field label="操作者姓名"><input className={inputClass} value={operatorName} onChange={(event) => setOperatorName(event.target.value)} disabled={!preview} /></Field><Field label="9 位工号"><input className={inputClass} inputMode="numeric" maxLength={9} value={employeeId} onChange={(event) => setEmployeeId(event.target.value)} disabled={!preview} /></Field><PrimaryButton className="w-full" disabled={!preview || !!busy || !operatorName.trim() || !/^\d{9}$/.test(employeeId)} onClick={() => void confirm()}><CheckCircle2 className="size-4" />{busy === 'confirm' ? '提交中…' : '确认并提交平台'}</PrimaryButton></div></Card>
          <div><h2 className="mb-3 font-semibold">提交记录</h2>{submissions.length === 0 ? <Card className="p-5 text-sm text-slate-500">暂无提交记录</Card> : <div className="space-y-3">{submissions.map((submission) => <SubmissionCard key={submission.id} submission={submission} busy={busy === submission.id} onReconcile={() => void act(submission.id, 'reconcile')} onRetry={() => void act(submission.id, 'retry')} />)}</div>}</div>
        </div>
      </div>
    </div>
  )
}
