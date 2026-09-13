import { useEffect, useState } from 'react'
import { FileSearch, X } from 'lucide-react'

import { api } from '../api/client'
import { ErrorMessage, Loading, SecondaryButton } from './ui'

interface EvidenceData {
  id: string
  section_type: string
  safe_excerpt: string | null
  purged_at: string | null
}

export function EvidenceDrawer({ evidenceId, onClose }: { evidenceId: string | null; onClose: () => void }) {
  const [result, setResult] = useState<{ id: string; data?: EvidenceData; error?: unknown } | null>(null)

  useEffect(() => {
    if (!evidenceId) return
    void api.getEvidence(evidenceId)
      .then((data) => setResult({ id: evidenceId, data }))
      .catch((error: unknown) => setResult({ id: evidenceId, error }))
  }, [evidenceId])

  if (!evidenceId) return null
  const current = result?.id === evidenceId ? result : null
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/25" role="dialog" aria-modal="true" aria-label="证据详情">
      <button className="min-w-0 flex-1 cursor-default" onClick={onClose} aria-label="关闭证据详情" />
      <aside className="h-full w-full max-w-lg overflow-y-auto bg-white p-6 shadow-2xl sm:p-8">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-semibold text-brand">证据锚点</p>
            <h2 className="mt-1 text-xl font-semibold">邮件来源片段</h2>
          </div>
          <SecondaryButton onClick={onClose} aria-label="关闭">
            <X className="size-4" aria-hidden="true" />
          </SecondaryButton>
        </div>
        <div className="mt-8">
          {current?.error ? <ErrorMessage error={current.error} /> : !current?.data ? <Loading label="正在读取证据" /> : current.data.purged_at || !current.data.safe_excerpt ? (
            <div className="rounded-xl bg-slate-100 p-5 text-sm text-slate-600">该证据已按保留策略清理。</div>
          ) : (
            <div>
              <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
                <FileSearch className="size-4" aria-hidden="true" />
                {current.data.section_type}
              </div>
              <pre className="mt-4 whitespace-pre-wrap break-words rounded-xl border border-slate-200 bg-slate-50 p-5 font-sans text-sm leading-7 text-slate-700">
                {current.data.safe_excerpt}
              </pre>
            </div>
          )}
        </div>
      </aside>
    </div>
  )
}
