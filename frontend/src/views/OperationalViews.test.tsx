import '@testing-library/jest-dom/vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ActionReportPayload, RunState } from '../types'
import { ActionsView } from './ActionsView'
import { ReportsView } from './ReportsView'
import { S1View } from './S1View'

afterEach(() => {
  cleanup()
})

const sampleRun: RunState = {
  run_id: 'run-1',
  status: 'completed',
  created_at: '2026-03-31T18:00:00Z',
  kind: 's1',
  result: {
    reference_date: '2026-03-31',
    source: { source: 'data' },
    summary: {
      horizon_days: 7,
      include_previsions: false,
      feasibility_mode: 'projected',
      besoins_s1: 12,
      matched_ofs: 8,
      feasible_ofs: 5,
      non_feasible_ofs: 3,
      action_components: 2,
      kanban_postes: 1,
    },
    of_results: [
      {
        num_of: 'OF-100',
        article: 'PF-ALPHA',
        date_debut: '2026-04-01',
        date_fin: '2026-04-02',
        qte_restante: 42,
        commande: 'CMD-200',
        commande_article: 'ART-200',
        commande_date_expedition: '2026-04-03',
        matching_method: 'MTS',
        feasible: false,
        missing_components: { COMP_X: 3, COMP_Y: 1 },
        alerts: ['Alerte'],
      },
    ],
    action_report: {
      component_lines: [],
      supplier_lines: [],
      poste_kanban_lines: [],
      impacted_ofs: 1,
      impacted_commandes: 1,
    },
    reports: {
      actions: {
        type: 'actions',
        path: '/tmp/actions.md',
        exists: true,
        content: '# Actions',
        updated_at: '2026-03-31T18:10:00Z',
      },
      s1: {
        type: 's1',
        path: '/tmp/s1.md',
        exists: true,
        content: '# S1',
        updated_at: '2026-03-31T18:10:00Z',
      },
    },
  },
}

const sampleActionReport: ActionReportPayload = {
  component_lines: [
    {
      article_composant: 'COMP_X',
      missing_qty_total: 12,
      nb_commandes_impactees: 3,
      nb_ofs_impactes: 2,
      niveau_action: 'RETARD_FOURNISSEUR',
      action_recommandee: 'Relancer',
    },
  ],
  supplier_lines: [
    {
      fournisseur: 'SUP-01',
      num_commande_achat: 'CA-99',
      articles_concernes: ['COMP_X', 'COMP_Y'],
    },
  ],
  poste_kanban_lines: [
    {
      poste_fournisseur: 'PP_145',
      libelle_poste_fournisseur: 'PREREGLAGE',
      articles_kanban_concernes: ['MH7624'],
      action_recommandee: 'Maintenir',
    },
  ],
  impacted_ofs: 2,
  impacted_commandes: 3,
}

describe('Operational views', () => {
  it('opens OF detail from S1View', () => {
    const onInspect = vi.fn()

    const { container } = render(<S1View runState="ready" data={sampleRun} onInspect={onInspect} />)

    const firstTableRow = container.querySelector('tbody tr')
    if (!firstTableRow) {
      throw new Error('Expected at least one table row')
    }
    fireEvent.click(firstTableRow)

    expect(onInspect).toHaveBeenCalled()
    expect(screen.getByText('S+1 workbench')).toBeInTheDocument()
    expect(screen.getAllByText('Bloqué').length).toBeGreaterThanOrEqual(1)
  })

  it('filters the S+1 table by blocked rows and search query', () => {
    const onInspect = vi.fn()
    const mixedRun: RunState = {
      ...sampleRun,
      result: {
        ...sampleRun.result!,
        of_results: [
          ...sampleRun.result!.of_results,
          {
            num_of: 'OF-101',
            article: 'PF-BETA',
            date_debut: '2026-04-02',
            date_fin: '2026-04-03',
            qte_restante: 20,
            commande: 'CMD-201',
            commande_article: 'ART-201',
            commande_date_expedition: '2026-04-04',
            matching_method: 'NOR',
            feasible: true,
            missing_components: {},
            alerts: [],
          },
        ],
      },
    }

    const { container } = render(<S1View runState="ready" data={mixedRun} onInspect={onInspect} />)

    fireEvent.click(screen.getByRole('button', { name: /^Bloqués$/ }))
    expect(container.querySelectorAll('tbody tr').length).toBeLessThanOrEqual(2)
    expect(container.querySelector('tbody')?.textContent).toContain('OF-100')
    expect(screen.queryByText('OF-101')).not.toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText('Rechercher OF, article, commande, composant...'), {
      target: { value: 'PF-ALPHA' },
    })
    expect(container.querySelectorAll('tbody tr')).toHaveLength(1)
  })

  it('renders actions and forwards detail inspection', () => {
    const onInspect = vi.fn()

    render(<ActionsView data={sampleActionReport} onInspect={onInspect} />)

    fireEvent.click(screen.getByText('SUP-01'))

    expect(screen.getByText('Composants bloquants')).toBeInTheDocument()
    expect(screen.getByText('Fournisseurs et postes kanban')).toBeInTheDocument()
    expect(onInspect).toHaveBeenCalledTimes(1)
  })

  it('renders reports and refresh action', () => {
    const onInspect = vi.fn()
    const onRefresh = vi.fn()

    render(
      <ReportsView
        reports={[
          {
            name: 's1_action_report.md',
            path: '/tmp/s1_action_report.md',
            category: 'actions',
            updated_at: '2026-03-31T18:10:00Z',
            size_bytes: 4096,
          },
        ]}
        embeddedReports={sampleRun.result?.reports ?? null}
        onInspect={onInspect}
        onRefresh={onRefresh}
      />,
    )

    fireEvent.click(screen.getByText('Rafraîchir'))
    fireEvent.click(screen.getByText('s1_action_report.md'))

    expect(onRefresh).toHaveBeenCalled()
    expect(onInspect).toHaveBeenCalled()
    expect(screen.getByText('Markdown disponibles')).toBeInTheDocument()
  })
})
