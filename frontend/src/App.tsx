import { Navigate, Route, Routes } from 'react-router-dom'

import { AppShell } from './components/AppShell'
import { ImportPage } from './pages/ImportPage'
import { PlanEditPage } from './pages/PlanEditPage'
import { PlanListPage } from './pages/PlanListPage'
import { ReviewPage } from './pages/ReviewPage'
import { SubmitPage } from './pages/SubmitPage'

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate replace to="/imports/new" />} />
        <Route path="imports/new" element={<ImportPage />} />
        <Route path="plans" element={<PlanListPage />} />
        <Route path="plans/:planId/edit" element={<PlanEditPage />} />
        <Route path="plans/:planId/review" element={<ReviewPage />} />
        <Route path="plans/:planId/submit" element={<SubmitPage />} />
        <Route path="*" element={<Navigate replace to="/imports/new" />} />
      </Route>
    </Routes>
  )
}
