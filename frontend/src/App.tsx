import {
  ClipboardCheck,
  FilePenLine,
  Inbox,
  ListChecks,
  Send,
  Sparkles,
} from 'lucide-react'
import { Link, NavLink, Navigate, Route, Routes } from 'react-router-dom'

const navigation = [
  { to: '/imports/new', label: '导入邮件', icon: Inbox },
  { to: '/plans', label: '计划列表', icon: ListChecks },
  { to: '/plans/demo/edit', label: '计划编辑', icon: FilePenLine },
  { to: '/plans/demo/review', label: '计划审核', icon: ClipboardCheck },
  { to: '/plans/demo/submit', label: '预览提交', icon: Send },
]

const pageCopy: Record<string, { eyebrow: string; title: string; description: string }> = {
  '/imports/new': {
    eyebrow: '第一步',
    title: '从邮件开始一份测试计划',
    description: '上传一封 .eml 邮件，系统将提取可追溯的需求事实并生成待审核草稿。',
  },
  '/plans': {
    eyebrow: '工作台',
    title: '测试计划',
    description: '集中查看草稿、待审核和已提交计划，后续阶段将在此接入真实数据。',
  },
  '/plans/demo/edit': {
    eyebrow: '草稿',
    title: '编辑计划与证据',
    description: '计划字段、领域明细和证据锚点将在阶段 3 接入不可变版本机制。',
  },
  '/plans/demo/review': {
    eyebrow: '人工审核',
    title: '确认规则与来源',
    description: '审核人可核对来源、处理警告，并以姓名和 9 位工号提交审计声明。',
  },
  '/plans/demo/submit': {
    eyebrow: '最终确认',
    title: '预览平台报文',
    description: '确认报文哈希与版本后再提交；前端不会直接访问 Mock Gateway。',
  },
}

function ShellPage({ path }: { path: keyof typeof pageCopy }) {
  const copy = pageCopy[path]
  return (
    <section className="mx-auto max-w-6xl px-5 py-12 sm:px-8 lg:py-20">
      <div className="rounded-3xl border border-slate-200 bg-white p-7 shadow-soft sm:p-12">
        <span className="text-sm font-semibold tracking-wide text-brand">{copy.eyebrow}</span>
        <h1 className="mt-3 max-w-3xl text-3xl font-semibold tracking-tight text-ink sm:text-5xl">
          {copy.title}
        </h1>
        <p className="mt-5 max-w-2xl text-base leading-7 text-slate-600">{copy.description}</p>
        <div className="mt-10 rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
          <Sparkles className="mx-auto size-8 text-brand" aria-hidden="true" />
          <p className="mt-3 font-medium text-slate-700">阶段 0 工程空壳已就绪</p>
          <p className="mt-1 text-sm text-slate-500">业务交互会在后续阶段按冻结计划逐步启用。</p>
        </div>
      </div>
    </section>
  )
}

export function App() {
  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="border-b border-slate-200 bg-white/95">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-6 px-5 py-4 sm:px-8">
          <Link className="flex items-center gap-3 font-semibold" to="/imports/new">
            <span className="grid size-9 place-items-center rounded-xl bg-brand text-white">
              <Sparkles className="size-5" aria-hidden="true" />
            </span>
            <span>邮件测试计划</span>
          </Link>
          <nav aria-label="主要导航" className="hidden items-center gap-1 lg:flex">
            {navigation.map(({ to, label, icon: Icon }) => (
              <NavLink
                className={({ isActive }) =>
                  `flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium transition-colors ${
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
          <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700">
            MVP · 阶段 0
          </span>
        </div>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Navigate replace to="/imports/new" />} />
          {Object.keys(pageCopy).map((path) => (
            <Route key={path} path={path} element={<ShellPage path={path} />} />
          ))}
          <Route path="*" element={<Navigate replace to="/imports/new" />} />
        </Routes>
      </main>
    </div>
  )
}
