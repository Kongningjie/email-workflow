import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { App } from './App'

describe('App', () => {
  it('展示阶段 0 的邮件导入空壳', () => {
    render(
      <MemoryRouter initialEntries={['/imports/new']}>
        <App />
      </MemoryRouter>,
    )

    expect(screen.getByRole('heading', { name: '从邮件开始一份测试计划' })).toBeInTheDocument()
    expect(screen.getByText('阶段 0 工程空壳已就绪')).toBeInTheDocument()
  })
})
