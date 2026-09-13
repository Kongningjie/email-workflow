import { useRef, useState } from 'react'
import { Mail, ShieldCheck, UploadCloud } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { api } from '../api/client'
import { Card, ErrorMessage, Notice, PageHeader, PrimaryButton } from '../components/ui'

export function ImportPage() {
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)

  async function submit() {
    if (!file || !confirmed) return
    setBusy(true)
    setError(null)
    try {
      const result = await api.importEmail(file, confirmed)
      if (result.test_plan_id) {
        navigate(`/plans/${result.test_plan_id}/edit`, {
          state: {
            message: result.deduplicated ? '该邮件已导入，已打开原计划。' : '邮件处理完成，草稿已生成。',
            warnings: result.warnings,
          },
        })
      } else {
        throw new Error(result.safe_error_summary ?? '邮件已接收，但未生成测试计划')
      }
    } catch (caught) {
      setError(caught)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader eyebrow="邮件导入" title="从一封邮件开始" description="上传单个 .eml 文件。系统只处理清洗后的正文，附件不会解析或发送给模型。" />
      <Card className="mt-8 overflow-hidden">
        <div className="grid md:grid-cols-[1fr_300px]">
          <div className="p-6 sm:p-10">
            <button
              type="button"
              className="flex min-h-64 w-full flex-col items-center justify-center rounded-2xl border-2 border-dashed border-slate-300 bg-slate-50 px-6 text-center transition hover:border-brand hover:bg-blue-50/40"
              onClick={() => inputRef.current?.click()}
            >
              <span className="grid size-14 place-items-center rounded-2xl bg-blue-50 text-brand">
                {file ? <Mail className="size-7" /> : <UploadCloud className="size-7" />}
              </span>
              <span className="mt-5 font-semibold text-ink">{file ? file.name : '选择 .eml 邮件文件'}</span>
              <span className="mt-2 text-sm text-slate-500">单文件，最大 5 MB</span>
            </button>
            <input
              ref={inputRef}
              className="sr-only"
              type="file"
              accept=".eml,message/rfc822"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              aria-label="选择 EML 文件"
            />
            <label className="mt-6 flex cursor-pointer items-start gap-3 rounded-xl border border-slate-200 p-4 text-sm leading-6 text-slate-700">
              <input className="mt-1 size-4 rounded border-slate-300 text-brand" type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
              <span>我确认清洗后的邮件内容将发送至阿里百炼 DashScope，用于一次结构化提取。</span>
            </label>
            {error ? <div className="mt-5"><ErrorMessage error={error} /></div> : null}
            <PrimaryButton className="mt-6 w-full" disabled={!file || !confirmed || busy} onClick={() => void submit()}>
              {busy ? '正在解析并生成草稿…' : '导入并生成计划'}
            </PrimaryButton>
          </div>
          <aside className="border-t border-slate-200 bg-slate-50 p-6 md:border-l md:border-t-0 sm:p-8">
            <ShieldCheck className="size-6 text-emerald-600" aria-hidden="true" />
            <h2 className="mt-4 font-semibold">处理边界</h2>
            <ul className="mt-4 space-y-3 text-sm leading-6 text-slate-600">
              <li>仅支持标准 .eml 文件</li>
              <li>主动内容和远程资源会移除</li>
              <li>附件不解析、不发送模型</li>
              <li>重复邮件不会再次调用模型</li>
            </ul>
            <div className="mt-6"><Notice>处理可能需要约一分钟，请勿重复上传。</Notice></div>
          </aside>
        </div>
      </Card>
    </div>
  )
}
