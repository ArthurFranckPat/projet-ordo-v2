import { useMemo, useState } from "react"
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  type ColumnDef,
  type SortingState,
  useReactTable,
} from "@tanstack/react-table"
import { ArrowDownWideNarrow, EyeOff, Search } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { DetailItem, OfResult, RunState } from "../types"

interface S1ViewProps {
  runState: "idle" | "loading" | "ready" | "error"
  data: RunState | null
  onInspect: (item: DetailItem) => void
}

function formatDate(value?: string | null) {
  if (!value) return "N/A"
  return new Date(value).toLocaleDateString("fr-FR")
}

function getStatusVariant(feasible: boolean) {
  return feasible ? "default" : "destructive"
}

export function S1View({ runState, data, onInspect }: S1ViewProps) {
  const result = data?.result ?? null
  const [search, setSearch] = useState("")
  const [statusFilter, setStatusFilter] = useState<"all" | "blocked" | "feasible">("all")
  const [sorting, setSorting] = useState<SortingState>([
    { id: "feasible", desc: false },
    { id: "date_debut", desc: false },
  ])
  const [showCommandContext, setShowCommandContext] = useState(true)

  const blockedRows = useMemo(
    () => (result?.of_results ?? []).filter((row) => !row.feasible),
    [result],
  )

  const filteredRows = useMemo(() => {
    const query = search.trim().toLowerCase()

    return (result?.of_results ?? []).filter((row) => {
      if (statusFilter === "blocked" && row.feasible) return false
      if (statusFilter === "feasible" && !row.feasible) return false
      if (!query) return true

      const haystack = [
        row.num_of,
        row.article,
        row.commande,
        row.commande_article,
        ...Object.keys(row.missing_components),
      ]
        .join(" ")
        .toLowerCase()

      return haystack.includes(query)
    })
  }, [result, search, statusFilter])

  const columns = useMemo<ColumnDef<OfResult>[]>(
    () => [
      {
        accessorKey: "num_of",
        header: "OF",
        cell: ({ row }) => (
          <div className="space-y-1">
            <div className="font-medium text-foreground">{row.original.num_of}</div>
            <div className="text-xs text-muted-foreground">{row.original.matching_method}</div>
          </div>
        ),
      },
      {
        accessorKey: "article",
        header: "Article",
      },
      {
        accessorKey: "commande",
        header: "Commande",
        enableHiding: true,
        cell: ({ row }) => (
          <div className="space-y-1">
            <div>{row.original.commande}</div>
            <div className="text-xs text-muted-foreground">{row.original.commande_article}</div>
          </div>
        ),
      },
      {
        accessorKey: "date_debut",
        header: "Début OF",
        cell: ({ getValue }) => formatDate(getValue<string | null>()),
      },
      {
        accessorKey: "date_fin",
        header: "Fin OF",
        cell: ({ getValue }) => formatDate(getValue<string | null>()),
      },
      {
        accessorKey: "qte_restante",
        header: "Qté",
      },
      {
        accessorKey: "feasible",
        header: "Statut",
        sortingFn: (rowA, rowB) => Number(rowA.original.feasible) - Number(rowB.original.feasible),
        cell: ({ row }) => (
          <Badge variant={getStatusVariant(row.original.feasible)}>
            {row.original.feasible ? "Faisable" : "Bloqué"}
          </Badge>
        ),
      },
      {
        id: "missing_components",
        header: "Manquants",
        cell: ({ row }) => {
          const entries = Object.entries(row.original.missing_components)
          if (entries.length === 0) {
            return <span className="text-muted-foreground">-</span>
          }

          return (
            <div className="flex flex-wrap gap-1.5">
              {entries.slice(0, 4).map(([name, qty]) => (
                <Badge key={`${row.original.num_of}-${name}`} variant="destructive" className="gap-1">
                  <span>{name}</span>
                  <strong>{qty}</strong>
                </Badge>
              ))}
            </div>
          )
        },
      },
    ],
    [],
  )

  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data: filteredRows,
    columns,
    state: {
      sorting,
      columnVisibility: {
        commande: showCommandContext,
      },
    },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  if (runState === "loading") {
    return (
      <Card className="border-border/70 bg-background/85 shadow-sm">
        <CardContent className="px-6 py-12">
          <div className="space-y-2 text-center">
            <p className="font-medium text-foreground">Run S+1 en cours</p>
            <p className="text-sm text-muted-foreground">
              Le workbench se mettra à jour dès que le backend aura terminé.
            </p>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!result) {
    return (
      <Card className="border-border/70 bg-background/85 shadow-sm">
        <CardContent className="px-6 py-12">
          <div className="space-y-2 text-center">
            <p className="font-medium text-foreground">Aucun run S+1 disponible</p>
            <p className="text-sm text-muted-foreground">
              Lancez un premier run depuis `Home` pour ouvrir ce workbench.
            </p>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <section className="space-y-6">
      <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr_0.9fr]">
        <Card className="border-border/70 bg-background/85 shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Priorité immédiate
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 pt-0">
            <div className="text-xl font-semibold text-foreground">
              {blockedRows[0]?.num_of ?? "Aucune"}
            </div>
            <p className="text-sm text-muted-foreground">
              {blockedRows[0]
                ? `${blockedRows[0].article} · ${blockedRows[0].commande}`
                : "Aucun OF bloqué à traiter en priorité"}
            </p>
          </CardContent>
        </Card>
        <Card className="border-border/70 bg-background/85 shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">OF bloqués</CardTitle>
          </CardHeader>
          <CardContent className="pt-0 text-3xl font-semibold tracking-tight text-foreground">
            {result.summary.non_feasible_ofs}
          </CardContent>
        </Card>
        <Card className="border-border/70 bg-background/85 shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Composants d’action
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0 text-3xl font-semibold tracking-tight text-foreground">
            {result.summary.action_components}
          </CardContent>
        </Card>
      </div>

      <Card className="border-border/70 bg-background/85 shadow-sm">
        <CardHeader className="gap-4">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div className="space-y-1">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                S+1 workbench
              </p>
              <CardTitle className="text-2xl tracking-tight">Faisabilité OF</CardTitle>
              <p className="text-sm text-muted-foreground">
                Réf. {formatDate(result.reference_date)} · horizon {result.summary.horizon_days} jours
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant={statusFilter === "all" ? "default" : "outline"}
                onClick={() => setStatusFilter("all")}
              >
                Tous
              </Button>
              <Button
                type="button"
                variant={statusFilter === "blocked" ? "default" : "outline"}
                onClick={() => setStatusFilter("blocked")}
              >
                Bloqués
              </Button>
              <Button
                type="button"
                variant={statusFilter === "feasible" ? "default" : "outline"}
                onClick={() => setStatusFilter("feasible")}
              >
                Faisables
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setShowCommandContext((value) => !value)}
              >
                <EyeOff className="mr-2 size-4" />
                {showCommandContext ? "Masquer commande" : "Afficher commande"}
              </Button>
            </div>
          </div>
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="relative w-full max-w-xl">
              <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Rechercher OF, article, commande, composant..."
                className="pl-10"
              />
            </div>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <ArrowDownWideNarrow className="size-4" />
              Tri par défaut: bloqués d’abord puis date OF
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {blockedRows.length > 0 ? (
            <div className="rounded-xl border border-destructive/20 bg-destructive/5 px-4 py-3 text-sm">
              <p className="font-medium text-foreground">À traiter en premier</p>
              <p className="mt-1 text-muted-foreground">
                {blockedRows
                  .slice(0, 3)
                  .map((row) => `${row.num_of} · ${row.article}`)
                  .join(" • ")}
              </p>
            </div>
          ) : null}

          <div className="overflow-hidden rounded-xl border">
            <Table>
              <TableHeader className="bg-muted/50">
                {table.getHeaderGroups().map((headerGroup) => (
                  <TableRow key={headerGroup.id}>
                    {headerGroup.headers.map((header) => (
                      <TableHead key={header.id} className="sticky top-0 bg-muted/50">
                        {header.isPlaceholder
                          ? null
                          : flexRender(header.column.columnDef.header, header.getContext())}
                      </TableHead>
                    ))}
                  </TableRow>
                ))}
              </TableHeader>
              <TableBody>
                {table.getRowModel().rows.length > 0 ? (
                  table.getRowModel().rows.map((row) => (
                    <TableRow
                      key={row.id}
                      data-state={row.original.feasible ? undefined : "selected"}
                      className="cursor-pointer"
                      onClick={() =>
                        onInspect({
                          title: row.original.num_of,
                          description: `${row.original.article} · ${row.original.commande}`,
                          payload: row.original,
                        })
                      }
                    >
                      {row.getVisibleCells().map((cell) => (
                        <TableCell key={cell.id}>
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={table.getVisibleLeafColumns().length} className="h-28 text-center text-muted-foreground">
                      Aucun OF ne correspond au filtre actuel.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </section>
  )
}
