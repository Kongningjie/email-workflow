import { useEffect, useState } from 'react'
import { ArrowRight, Plus } from 'lucide-react'
import { Link } from 'react-router-dom'

import { api } from '../api/client'
import type { Plan, PlanSummary } from '../api/types'
import { Card, EmptyState, ErrorMessage, Loading, PageHeader, StatusBadge } from '../components/ui'
import { formatDateTime } from '../components/utils'

type PlanRow = PlanSummary & { name?: string; project?: string }

export function PlanListPage() {
  const [plans, setPlans] = useState<PlanRow[] | null>(null)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    void api.listPlans().then(async (summaries) => {
      const details = await Promise.allSettled(summaries.map((item) => api.getPlan(item.id)))
      setPlans(summaries.map((item, index) => {
        const detail = details[index]
        const plan = detail.status === 'fulfilled' ? (detail.value as Plan) : null
        return { ...item, name: plan?.version.content.plan_name, project: plan?.version.content.project_name }
      }))
    }).catch(setError)
  }, [])

  return (
    <div>
      <PageHeader
        eyebrow="工作台"
        title="测试计划"
        description="查看计划当前状态，继续编辑、审核或处理平台提交。"
        actions={<Link className="inline-flex min-h-10 items-center gap-2 rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700" to="/imports/new"><Plus className="size-4" />导入邮件</Link>}
      />
      <Card className="mt-8 overflow-hidden">
        {error ? <div className="p-6"><ErrorMessage error={error} /></div> : !plans ? <Loading label="正在读取计划" /> : plans.length === 0 ? (
          <EmptyState title="还没有测试计划" description="导入第一封 .eml 邮件后，生成的草稿会出现在这里。" action={<Link className="font-semibold text-brand" to="/imports/new">立即导入</Link>} />
        ) : (
          <div className="divide-y divide-slate-100">
            {plans.map((plan) => (
              <Link key={plan.id} to={`/plans/${plan.id}/edit`} className="group grid gap-3 p-5 hover:bg-slate-50 sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:items-center sm:gap-8 sm:p-6">
                <div className="min-w-0">
                  <h2 className="truncate font-semibold text-ink group-hover:text-brand">{plan.name || '未命名测试计划'}</h2>
                  <p className="mt-1 truncate text-sm text-slate-500">{plan.project || '项目待填写'} · 版本 {plan.current_version}</p>
                </div>
                <div className="flex items-center gap-3"><StatusBadge status={plan.status} /><span className="text-xs text-slate-400">{formatDateTime(plan.updated_at)}</span></div>
                <ArrowRight className="hidden size-5 text-slate-300 transition group-hover:translate-x-1 group-hover:text-brand sm:block" aria-hidden="true" />
              </Link>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
