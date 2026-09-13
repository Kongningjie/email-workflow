import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { AlertCircle, CheckCircle2, Info, LoaderCircle, XCircle } from 'lucide-react'

import type { PlanStatus, Provenance } from '../api/types'

const statusLabels: Record<string, string> = {
  draft: '草稿',
  pending_review: '待审核',
  revision_requested: '需修改',
  approved: '已批准',
  submitting: '提交中',
  submitted: '已提交',
  submission_failed: '提交失败',
  unknown: '结果未知',
}

const statusStyles: Record<string, string> = {
  draft: 'bg-slate-100 text-slate-700',
  pending_review: 'bg-blue-50 text-blue-700',
  revision_requested: 'bg-amber-50 text-amber-800',
  approved: 'bg-emerald-50 text-emerald-700',
  submitting: 'bg-blue-50 text-blue-700',
  submitted: 'bg-emerald-50 text-emerald-700',
  submission_failed: 'bg-rose-50 text-rose-700',
  unknown: 'bg-amber-50 text-amber-800',
}

export function StatusBadge({ status }: { status: PlanStatus | string }) {
  return (
    <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${statusStyles[status] ?? statusStyles.draft}`}>
      {statusLabels[status] ?? status}
    </span>
  )
}

const provenanceLabels: Record<Provenance, string> = {
  source: '邮件来源',
  model_suggestion: '模型建议',
  derived: '规则推导',
  user_provided: '人工填写',
  unresolved: '待确认',
}

const provenanceStyles: Record<Provenance, string> = {
  source: 'bg-emerald-50 text-emerald-700',
  model_suggestion: 'bg-violet-50 text-violet-700',
  derived: 'bg-sky-50 text-sky-700',
  user_provided: 'bg-slate-100 text-slate-700',
  unresolved: 'bg-amber-50 text-amber-800',
}

export function ProvenanceBadge({ value }: { value: Provenance }) {
  return (
    <span className={`rounded-md px-2 py-0.5 text-xs font-medium ${provenanceStyles[value]}`}>
      {provenanceLabels[value]}
    </span>
  )
}

export function Button({ className = '', children, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={`inline-flex min-h-10 items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}

export function PrimaryButton(props: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <Button {...props} className={`bg-brand text-white hover:bg-blue-700 ${props.className ?? ''}`} />
}

export function SecondaryButton(props: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <Button
      {...props}
      className={`border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 ${props.className ?? ''}`}
    />
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-2xl border border-slate-200 bg-white shadow-card ${className}`}>{children}</section>
}

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow: string; title: string; description: string; actions?: ReactNode }) {
  return (
    <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p className="text-sm font-semibold text-brand">{eyebrow}</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-ink sm:text-4xl">{title}</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600 sm:text-base">{description}</p>
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
    </div>
  )
}

export function Notice({ tone = 'info', children }: { tone?: 'info' | 'success' | 'warning' | 'error'; children: ReactNode }) {
  const variants = {
    info: ['border-blue-200 bg-blue-50 text-blue-800', Info],
    success: ['border-emerald-200 bg-emerald-50 text-emerald-800', CheckCircle2],
    warning: ['border-amber-200 bg-amber-50 text-amber-900', AlertCircle],
    error: ['border-rose-200 bg-rose-50 text-rose-800', XCircle],
  } as const
  const [style, Icon] = variants[tone]
  return (
    <div className={`flex items-start gap-3 rounded-xl border p-4 text-sm ${style}`} role={tone === 'error' ? 'alert' : 'status'}>
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <div className="min-w-0 leading-6">{children}</div>
    </div>
  )
}

export function Loading({ label = '正在加载' }: { label?: string }) {
  return (
    <div className="flex min-h-40 items-center justify-center gap-3 text-sm text-slate-500" role="status">
      <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
      {label}
    </div>
  )
}

export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return (
    <div className="px-6 py-16 text-center">
      <h2 className="font-semibold text-ink">{title}</h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">{description}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

export function ErrorMessage({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : '发生未知错误'
  return <Notice tone="error">{message}</Notice>
}

export function Field({ label, hint, error, children }: { label: string; hint?: string; error?: string; children: ReactNode }) {
  return (
    <label className="block text-sm font-medium text-slate-700">
      <span>{label}</span>
      {hint && <span className="ml-2 font-normal text-slate-400">{hint}</span>}
      <span className="mt-1.5 block">{children}</span>
      {error && <span className="mt-1 block text-xs text-rose-600">{error}</span>}
    </label>
  )
}
