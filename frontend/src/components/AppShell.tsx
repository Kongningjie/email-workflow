import { useState } from 'react'
import { Inbox, ListChecks, Menu, Sparkles, X } from 'lucide-react'
import { Link, NavLink, Outlet } from 'react-router-dom'

const navigation = [
  { to: '/imports/new', label: '导入邮件', icon: Inbox },
  { to: '/plans', label: '计划列表', icon: ListChecks },
]

export function AppShell() {
  const [open, setOpen] = useState(false)
  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-6 px-5 sm:px-8">
          <Link className="flex items-center gap-3 font-semibold" to="/imports/new">
            <span className="grid size-9 place-items-center rounded-xl bg-brand text-white">
              <Sparkles className="size-5" aria-hidden="true" />
            </span>
            <span>邮件测试计划</span>
          </Link>
          <nav aria-label="主要导航" className="hidden items-center gap-1 sm:flex">
            {navigation.map(({ to, label, icon: Icon }) => (
              <NavLink
                className={({ isActive }) =>
                  `flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition-colors ${
                    isActive ? 'bg-blue-50 text-brand' : 'text-slate-600 hover:bg-slate-50 hover:text-ink'
                  }`
                }
                key={to}
                to={to}
              >
                <Icon className="size-4" aria-hidden="true" />
                {label}
              </NavLink>
            ))}
          </nav>
          <div className="flex items-center gap-2">
            <span className="hidden rounded-full bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700 md:inline-flex">
              MVP · 阶段 5
            </span>
            <button className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 sm:hidden" onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-label="打开导航">
              {open ? <X className="size-5" /> : <Menu className="size-5" />}
            </button>
          </div>
        </div>
        {open && (
          <nav className="border-t border-slate-100 bg-white px-5 py-3 sm:hidden" aria-label="移动端导航">
            {navigation.map(({ to, label }) => (
              <NavLink key={to} to={to} onClick={() => setOpen(false)} className="block rounded-lg px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
                {label}
              </NavLink>
            ))}
          </nav>
        )}
      </header>
      <main className="mx-auto max-w-7xl px-5 py-8 sm:px-8 sm:py-12">
        <Outlet />
      </main>
      <footer className="mx-auto max-w-7xl px-5 py-8 text-xs text-slate-400 sm:px-8">
        服务端负责规则、版本和提交权限的最终判定
      </footer>
    </div>
  )
}
