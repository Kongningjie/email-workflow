import { ClipboardCheck, FilePenLine, Send } from 'lucide-react'
import { NavLink } from 'react-router-dom'

export function PlanTabs({ planId }: { planId: string }) {
  const tabs = [
    { to: `/plans/${planId}/edit`, label: '编辑与证据', icon: FilePenLine },
    { to: `/plans/${planId}/review`, label: '规则与审核', icon: ClipboardCheck },
    { to: `/plans/${planId}/submit`, label: '预览与提交', icon: Send },
  ]
  return (
    <nav className="flex gap-1 overflow-x-auto rounded-xl border border-slate-200 bg-white p-1" aria-label="计划操作">
      {tabs.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            `flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium ${
              isActive ? 'bg-blue-50 text-brand' : 'text-slate-600 hover:bg-slate-50'
            }`
          }
        >
          <Icon className="size-4" aria-hidden="true" />
          {label}
        </NavLink>
      ))}
    </nav>
  )
}
