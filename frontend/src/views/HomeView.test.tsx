import '@testing-library/jest-dom/vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { HomeView } from './HomeView'

afterEach(() => {
  cleanup()
})

describe('HomeView', () => {
  it('renders data sources and triggers actions', () => {
    const setSource = vi.fn()
    const onLoadSource = vi.fn()
    const onRunS1 = vi.fn()

    render(
      <HomeView
        source="data"
        setSource={setSource}
        loadState="ready"
        runState="idle"
        lastSourceSnapshot={{ source: 'data' }}
        onLoadSource={onLoadSource}
        onRunS1={onRunS1}
      />,
    )

    expect(screen.getByRole('button', { name: /csv versionnés/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /exports récents erp/i })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /exports récents erp/i }))
    expect(setSource).toHaveBeenCalledWith('downloads')

    fireEvent.click(screen.getByText('Charger la source'))
    expect(onLoadSource).toHaveBeenCalled()

    fireEvent.click(screen.getByText('Lancer le run S+1'))
    expect(onRunS1).toHaveBeenCalled()
  })

  it('renders a structured readiness summary', () => {
    render(
      <HomeView
        source="data"
        setSource={() => {}}
        loadState="ready"
        runState="idle"
        lastSourceSnapshot={{
          source: 'data',
          loaded_at: '2026-03-31T18:10:00Z',
          counts: {
            ofs: 120,
            commandes_clients: 87,
            articles: 6400,
            receptions: 300,
          },
        }}
        onLoadSource={() => {}}
        onRunS1={() => {}}
      />,
    )

    expect(screen.getByText('Résumé de préparation')).toBeInTheDocument()
    expect(screen.getByText('Source chargée')).toBeInTheDocument()
    expect(screen.getByText('Volume chargé')).toBeInTheDocument()
    expect(screen.queryAllByText('Prêt à lancer').length).toBeGreaterThan(0)
  })
})
