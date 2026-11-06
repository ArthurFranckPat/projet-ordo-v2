import { useEffect, useMemo, useState } from "react"
import { PackageSearch, PanelsTopLeft, Settings2, Siren, Table2 } from "lucide-react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarSeparator,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import "./index.css"
import { ApiError, apiClient } from "./api/client"
import type { ApiConfig, DataSource, DetailItem, ReportFile, RunState } from "./types"
import { ActionsView } from "./views/ActionsView"
import { HomeView } from "./views/HomeView"
import { ReportsView } from "./views/ReportsView"
import { S1View } from "./views/S1View"

type ViewKey = "home" | "s1" | "actions" | "reports" | "settings"
type LoadState = "idle" | "loading" | "ready" | "error"
type RunStateStatus = "idle" | "loading" | "ready" | "error"

const VIEW_ITEMS: Array<{
  key: ViewKey
  label: string
  hint: string
  icon: typeof PanelsTopLeft
}> = [
  { key: "home", label: "Home", hint: "Sources + lancement", icon: PanelsTopLeft },
  { key: "s1", label: "S+1", hint: "Workbench OF", icon: Table2 },
  { key: "actions", label: "Actions", hint: "Appro + kanban", icon: Siren },
  { key: "reports", label: "Reports", hint: "Markdown générés", icon: PackageSearch },
  { key: "settings", label: "Settings", hint: "Info locale", icon: Settings2 },
]

function formatTimestamp(value?: string | null) {
  if (!value) return "N/A"
  try {
    return new Date(value).toLocaleString("fr-FR")
  } catch {
    return value
  }
}

async function pollRunUntilSettled(runId: string) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    const run = await apiClient.getRun(runId)
    if (run.status !== "running") {
      return run
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1000))
  }
  throw new ApiError("Le run S+1 est resté en attente trop longtemps.")
}

function getBadgeVariant(state: "checking" | "ready" | "error" | LoadState | RunStateStatus) {
  if (state === "ready") return "default"
  if (state === "error") return "destructive"
  if (state === "loading" || state === "checking") return "secondary"
  return "outline"
}

function App() {
  const [activeView, setActiveView] = useState<ViewKey>("home")
  const [config, setConfig] = useState<ApiConfig | null>(null)
  const [reports, setReports] = useState<ReportFile[]>([])
  const [source, setSource] = useState<DataSource>("data")
  const [loadState, setLoadState] = useState<LoadState>("idle")
  const [runState, setRunState] = useState<RunStateStatus>("idle")
  const [backendState, setBackendState] = useState<"checking" | "ready" | "error">("checking")
  const [lastRun, setLastRun] = useState<RunState | null>(null)
  const [lastSourceSnapshot, setLastSourceSnapshot] = useState<Record<string, unknown> | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [detailItem, setDetailItem] = useState<DetailItem | null>(null)

  useEffect(() => {
    let cancelled = false

    async function bootstrap() {
      try {
        const [health, appConfig, reportFiles] = await Promise.all([
          apiClient.getHealth(),
          apiClient.getConfig(),
          apiClient.listReports(),
        ])

        if (cancelled) return
        setBackendState(health.status === "ok" ? "ready" : "error")
        setConfig(appConfig)
        setReports(reportFiles)
        setErrorMessage(null)
      } catch (error) {
        if (cancelled) return
        const message =
          error instanceof ApiError
            ? error.message
            : "Impossible de joindre l’API locale. Lancez uvicorn src.api.server:app --reload."
        setBackendState("error")
        setErrorMessage(message)
      }
    }

    bootstrap()
    return () => {
      cancelled = true
    }
  }, [])

  const kpis = useMemo(() => {
    const summary = lastRun?.result?.summary
    return [
      { label: "OF matchés", value: summary?.matched_ofs ?? 0 },
      { label: "OF non faisables", value: summary?.non_feasible_ofs ?? 0 },
      { label: "Alertes composants", value: summary?.action_components ?? 0 },
      { label: "Postes kanban", value: summary?.kanban_postes ?? 0 },
    ]
  }, [lastRun])

  const activeViewItem = VIEW_ITEMS.find((item) => item.key === activeView)

  async function refreshReports() {
    try {
      setReports(await apiClient.listReports())
    } catch (error) {
      if (error instanceof ApiError) {
        setErrorMessage(error.message)
      }
    }
  }

  async function handleLoadSource() {
    setLoadState("loading")
    setErrorMessage(null)
    toast.loading(`Chargement de ${source === "data" ? "data/" : "Téléchargements"}...`, {
      id: "load-source",
    })
    try {
      const response = await apiClient.loadData(source)
      setLastSourceSnapshot(response)
      setLoadState("ready")
      toast.success("Source prête pour S+1", { id: "load-source" })
      await refreshReports()
    } catch (error) {
      setLoadState("error")
      const message = error instanceof ApiError ? error.message : "Chargement impossible."
      setErrorMessage(message)
      toast.error(message, { id: "load-source" })
    }
  }

  async function handleRunS1() {
    setRunState("loading")
    setErrorMessage(null)
    toast.loading("Exécution du run S+1...", { id: "run-s1" })
    try {
      const response = await apiClient.runS1({
        horizon: 7,
        include_previsions: false,
        feasibility_mode: "projected",
      })
      setLastRun(response)
      setActiveView("s1")
      const settledRun =
        response.status === "running" ? await pollRunUntilSettled(response.run_id) : response
      setLastRun(settledRun)
      setRunState(settledRun.status === "completed" ? "ready" : "error")
      if (settledRun.status === "failed") {
        const message = settledRun.error ?? "Le run S+1 a échoué."
        setErrorMessage(message)
        toast.error(message, { id: "run-s1" })
      } else {
        toast.success("Run S+1 terminé", { id: "run-s1" })
      }
      await refreshReports()
    } catch (error) {
      setRunState("error")
      const message = error instanceof ApiError ? error.message : "Exécution S+1 impossible."
      setErrorMessage(message)
      toast.error(message, { id: "run-s1" })
    }
  }

  return (
    <TooltipProvider>
      <SidebarProvider>
        <Sidebar variant="inset" collapsible="icon">
          <SidebarHeader className="gap-4 px-3 py-4">
            <div className="space-y-1 px-2">
              <span className="text-[11px] font-semibold uppercase tracking-[0.24em] text-muted-foreground">
                Industrial command center
              </span>
              <div className="flex items-center justify-between gap-2">
                <div>
                  <h1 className="text-xl font-semibold tracking-tight text-foreground">Ordo GUI</h1>
                  <p className="text-sm text-muted-foreground">
                    shadcn shell + workbenches métier
                  </p>
                </div>
                <Badge variant="secondary">{source}</Badge>
              </div>
            </div>
          </SidebarHeader>
          <SidebarSeparator />
          <SidebarContent>
            <SidebarGroup>
              <SidebarGroupLabel>Navigation</SidebarGroupLabel>
              <SidebarMenu>
                {VIEW_ITEMS.map((item) => {
                  const Icon = item.icon
                  return (
                    <SidebarMenuItem key={item.key}>
                      <SidebarMenuButton
                        isActive={activeView === item.key}
                        tooltip={item.label}
                        onClick={() => setActiveView(item.key)}
                      >
                        <Icon />
                        <span>{item.label}</span>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  )
                })}
              </SidebarMenu>
            </SidebarGroup>
          </SidebarContent>
          <SidebarFooter className="gap-2 p-3">
            <Card size="sm" className="border-sidebar-border bg-sidebar-accent/40 shadow-none">
              <CardContent className="grid gap-2 px-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs uppercase tracking-[0.12em] text-muted-foreground">API</span>
                  <Badge variant={getBadgeVariant(backendState)}>{backendState}</Badge>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs uppercase tracking-[0.12em] text-muted-foreground">Load</span>
                  <Badge variant={getBadgeVariant(loadState)}>{loadState}</Badge>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs uppercase tracking-[0.12em] text-muted-foreground">S+1</span>
                  <Badge variant={getBadgeVariant(runState)}>{runState}</Badge>
                </div>
              </CardContent>
            </Card>
          </SidebarFooter>
        </Sidebar>

        <SidebarInset className="min-h-screen bg-[radial-gradient(circle_at_top_left,rgba(21,94,239,0.10),transparent_28%),linear-gradient(180deg,#f8fafc_0%,#eef3f7_100%)]">
          <header className="sticky top-0 z-20 border-b bg-background/85 px-4 py-3 backdrop-blur md:px-6">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <SidebarTrigger />
                <div>
                  <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Workspace</p>
                  <h2 className="text-lg font-semibold tracking-tight text-foreground">
                    {activeViewItem?.label}
                  </h2>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline">Source {source}</Badge>
                <Badge variant="outline">
                  Dernier run {formatTimestamp(lastRun?.completed_at ?? lastRun?.created_at)}
                </Badge>
              </div>
            </div>
          </header>

          <main className="space-y-6 px-4 py-5 md:px-6">
            {errorMessage ? (
              <Card className="border-destructive/25 bg-destructive/5 shadow-none">
                <CardContent className="px-4 py-4">
                  <p className="font-medium text-foreground">Blocage UI/API</p>
                  <p className="mt-1 text-sm text-muted-foreground">{errorMessage}</p>
                </CardContent>
              </Card>
            ) : null}

            <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {kpis.map((kpi) => (
                <Card key={kpi.label} className="border-border/70 bg-background/80 shadow-sm">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium text-muted-foreground">
                      {kpi.label}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="pt-0">
                    <div className="text-3xl font-semibold tracking-tight text-foreground">
                      {kpi.value}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </section>

            {activeView === "home" ? (
              <HomeView
                source={source}
                setSource={setSource}
                loadState={loadState}
                runState={runState}
                lastSourceSnapshot={lastSourceSnapshot}
                onLoadSource={handleLoadSource}
                onRunS1={handleRunS1}
              />
            ) : null}

            {activeView === "s1" ? (
              <S1View
                runState={runState}
                data={lastRun}
                onInspect={(item: DetailItem) => setDetailItem(item)}
              />
            ) : null}

            {activeView === "actions" ? (
              <ActionsView
                data={lastRun?.result?.action_report ?? null}
                onInspect={(item: DetailItem) => setDetailItem(item)}
              />
            ) : null}

            {activeView === "reports" ? (
              <ReportsView
                reports={reports}
                embeddedReports={lastRun?.result?.reports ?? null}
                onInspect={(item: DetailItem) => setDetailItem(item)}
                onRefresh={refreshReports}
              />
            ) : null}

            {activeView === "settings" ? (
              <Card className="max-w-3xl border-border/70 bg-background/80 shadow-sm">
                <CardHeader>
                  <CardTitle>Configuration locale</CardTitle>
                </CardHeader>
                <CardContent className="grid gap-3 md:grid-cols-3">
                  <Card className="shadow-none">
                    <CardHeader>
                      <CardTitle className="text-sm">Sources disponibles</CardTitle>
                    </CardHeader>
                    <CardContent className="text-sm text-muted-foreground">
                      {config?.sources.map((entry) => entry.label).join(" / ") ?? "N/A"}
                    </CardContent>
                  </Card>
                  <Card className="shadow-none">
                    <CardHeader>
                      <CardTitle className="text-sm">Source par défaut</CardTitle>
                    </CardHeader>
                    <CardContent className="text-sm text-muted-foreground">
                      {config?.data_dir_default ?? "data/"}
                    </CardContent>
                  </Card>
                  <Card className="shadow-none">
                    <CardHeader>
                      <CardTitle className="text-sm">API backend</CardTitle>
                    </CardHeader>
                    <CardContent className="text-sm text-muted-foreground">
                      {backendState === "ready" ? "Connectée" : "À démarrer"}
                    </CardContent>
                  </Card>
                </CardContent>
              </Card>
            ) : null}
          </main>
        </SidebarInset>

        <Sheet open={Boolean(detailItem)} onOpenChange={(open) => !open && setDetailItem(null)}>
          <SheetContent side="right" className="w-[92vw] sm:max-w-2xl">
            <SheetHeader>
              <SheetTitle>{detailItem?.title ?? "Inspection"}</SheetTitle>
              <SheetDescription>
                {detailItem?.description ?? "Détail contextuel de la ligne sélectionnée."}
              </SheetDescription>
            </SheetHeader>
            <div className="mt-4 overflow-auto rounded-xl border bg-muted/30 p-4">
              <pre className="whitespace-pre-wrap break-words text-xs leading-6 text-muted-foreground">
                {JSON.stringify(detailItem?.payload ?? {}, null, 2)}
              </pre>
            </div>
          </SheetContent>
        </Sheet>
        <Toaster />
      </SidebarProvider>
    </TooltipProvider>
  )
}

export default App
