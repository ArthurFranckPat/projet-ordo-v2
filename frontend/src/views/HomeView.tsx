import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import type { DataSource } from "../types"

interface HomeViewProps {
  source: DataSource
  setSource: (value: DataSource) => void
  loadState: "idle" | "loading" | "ready" | "error"
  runState: "idle" | "loading" | "ready" | "error"
  lastSourceSnapshot: Record<string, unknown> | null
  onLoadSource: () => void
  onRunS1: () => void
}

const SOURCE_OPTIONS: DataSource[] = ["data", "downloads"]

function sourceLabel(source: DataSource) {
  return source === "data" ? "Répertoire data/" : "Téléchargements"
}

function formatTimestamp(value: unknown) {
  if (typeof value !== "string") return "N/A"
  try {
    return new Date(value).toLocaleString("fr-FR")
  } catch {
    return value
  }
}

function getLoadPhaseLabel(loadState: HomeViewProps["loadState"]) {
  switch (loadState) {
    case "loading":
      return "Lecture et validation des exports"
    case "ready":
      return "Source prête pour le run"
    case "error":
      return "Chargement à corriger"
    default:
      return "Source en attente"
  }
}

function getReadinessState(
  loadState: HomeViewProps["loadState"],
  runState: HomeViewProps["runState"],
) {
  if (runState === "loading") return "Run S+1 en cours"
  if (loadState === "ready") return "Prêt à lancer"
  if (loadState === "loading") return "Préparation"
  if (loadState === "error") return "Blocage"
  return "En attente"
}

function getVariant(state: HomeViewProps["loadState"] | HomeViewProps["runState"]) {
  if (state === "ready") return "default"
  if (state === "error") return "destructive"
  if (state === "loading") return "secondary"
  return "outline"
}

export function HomeView({
  source,
  setSource,
  loadState,
  runState,
  lastSourceSnapshot,
  onLoadSource,
  onRunS1,
}: HomeViewProps) {
  const loadedSource =
    typeof lastSourceSnapshot?.source === "string"
      ? (lastSourceSnapshot.source as DataSource)
      : null
  const counts =
    typeof lastSourceSnapshot?.counts === "object" && lastSourceSnapshot.counts !== null
      ? (lastSourceSnapshot.counts as Record<string, number>)
      : null

  return (
    <section className="grid gap-6 xl:grid-cols-[1.35fr_0.95fr]">
      <div className="space-y-6">
        <Card className="border-border/70 bg-background/85 shadow-sm">
          <CardHeader className="space-y-2">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                  Source
                </p>
                <CardTitle className="text-2xl tracking-tight">
                  Préparer les données avant S+1
                </CardTitle>
              </div>
              <Badge variant={getVariant(loadState)}>{getLoadPhaseLabel(loadState)}</Badge>
            </div>
            <CardDescription>
              Chargez un jeu de données stable ou les derniers exports ERP, vérifiez la préparation,
              puis enchaînez immédiatement sur le run `S+1`.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="grid gap-4 md:grid-cols-2">
              {SOURCE_OPTIONS.map((option) => {
                const selected = source === option
                return (
                  <button
                    key={option}
                    type="button"
                    onClick={() => setSource(option)}
                    className={[
                      "rounded-xl border p-4 text-left transition hover:border-primary/40 hover:bg-accent/20",
                      selected
                        ? "border-primary/40 bg-primary/5 ring-2 ring-primary/15"
                        : "border-border bg-card",
                    ].join(" ")}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                        {sourceLabel(option)}
                      </span>
                      <Badge variant={selected ? "default" : "outline"}>
                        {selected ? "Actif" : "Choisir"}
                      </Badge>
                    </div>
                    <div className="mt-3 space-y-1">
                      <p className="text-base font-semibold text-foreground">
                        {option === "data" ? "CSV versionnés" : "Exports récents ERP"}
                      </p>
                      <p className="text-sm text-muted-foreground">
                        {option === "data"
                          ? "Base stable pour replay, comparaison et débogage."
                          : "Mode terrain pour repartir des derniers téléchargements."}
                      </p>
                    </div>
                  </button>
                )
              })}
            </div>

            <div className="grid gap-3 md:grid-cols-3">
              {[
                {
                  step: "1. Source",
                  title: sourceLabel(source),
                  description:
                    source === "data"
                      ? "Sécurise les relectures et la comparaison de runs."
                      : "Cible les derniers exports opérationnels disponibles.",
                  badge: "Sélection",
                },
                {
                  step: "2. Chargement",
                  title: getLoadPhaseLabel(loadState),
                  description:
                    loadState === "loading"
                      ? "Comptage des entités, validation de la source et préparation du contexte."
                      : loadState === "ready"
                        ? "Le contexte est prêt côté frontend et API."
                        : "Aucun chargement utile n’a encore été validé.",
                  badge: loadState,
                },
                {
                  step: "3. Disponibilité",
                  title: getReadinessState(loadState, runState),
                  description:
                    loadState === "ready"
                      ? "Le prochain geste recommandé est le lancement du run S+1."
                      : "Le workbench S+1 reste verrouillé tant que la source n’est pas prête.",
                  badge: runState === "loading" ? runState : loadState,
                },
              ].map((item) => (
                <Card key={item.step} className="border-border/70 bg-muted/30 shadow-none">
                  <CardHeader className="gap-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                        {item.step}
                      </span>
                      <Badge variant={getVariant(item.badge as HomeViewProps["loadState"])}>{item.badge}</Badge>
                    </div>
                    <CardTitle className="text-base">{item.title}</CardTitle>
                    <CardDescription>{item.description}</CardDescription>
                  </CardHeader>
                </Card>
              ))}
            </div>

            <Separator />

            <div className="flex flex-wrap gap-3">
              <Button onClick={onLoadSource} disabled={loadState === "loading"} size="lg">
                {loadState === "loading" ? "Chargement en cours..." : "Charger la source"}
              </Button>
              <Button
                variant="outline"
                onClick={onRunS1}
                disabled={loadState !== "ready" || runState === "loading"}
                size="lg"
              >
                {runState === "loading" ? "Run S+1 en cours..." : "Lancer le run S+1"}
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border/70 bg-background/85 shadow-sm">
          <CardHeader>
            <CardTitle className="text-lg">Parcours recommandé</CardTitle>
            <CardDescription>
              L’objectif est d’emmener l’utilisateur vers le tableau `S+1` avec un contexte déjà
              prêt et sans ambiguïté sur l’état de chargement.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-2">
            {[
              "Choisir la bonne source de données.",
              "Charger et valider les volumes reçus.",
              "Confirmer le statut “prêt à lancer”.",
              "Lancer S+1 puis traiter d’abord les OF bloqués.",
            ].map((step) => (
              <div
                key={step}
                className="rounded-xl border border-border/70 bg-muted/25 px-4 py-3 text-sm text-muted-foreground"
              >
                {step}
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card className="border-border/70 bg-background/85 shadow-sm">
        <CardHeader className="space-y-2">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                Readiness
              </p>
              <CardTitle className="text-xl tracking-tight">Résumé de préparation</CardTitle>
            </div>
            <Badge variant={getVariant(loadState)}>{getReadinessState(loadState, runState)}</Badge>
          </div>
          <CardDescription>
            Une fois la source chargée, l’écran doit rendre évident le volume disponible, la fraîcheur
            du snapshot et le prochain geste attendu.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {loadState === "loading" ? (
            <div className="grid gap-3">
              <Skeleton className="h-24 rounded-xl" />
              <Skeleton className="h-24 rounded-xl" />
              <Skeleton className="h-24 rounded-xl" />
            </div>
          ) : lastSourceSnapshot ? (
            <div className="grid gap-3">
              <Card className="border-border/70 shadow-none">
                <CardContent className="grid gap-1 px-4 py-4">
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                    Source chargée
                  </span>
                  <strong className="text-base text-foreground">
                    {loadedSource ? sourceLabel(loadedSource) : "N/A"}
                  </strong>
                  <p className="text-sm text-muted-foreground">
                    {loadedSource === source
                      ? "La source active correspond au dernier chargement."
                      : "La source active diffère du dernier chargement, rechargez avant le run."}
                  </p>
                </CardContent>
              </Card>
              <Card className="border-border/70 shadow-none">
                <CardContent className="grid gap-1 px-4 py-4">
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                    Horodatage
                  </span>
                  <strong className="text-base text-foreground">
                    {formatTimestamp(lastSourceSnapshot.loaded_at)}
                  </strong>
                  <p className="text-sm text-muted-foreground">
                    Dernière préparation de données connue côté interface.
                  </p>
                </CardContent>
              </Card>
              <Card className="border-border/70 shadow-none">
                <CardContent className="grid gap-1 px-4 py-4">
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                    Volume chargé
                  </span>
                  <strong className="text-base text-foreground">
                    {counts
                      ? `${counts.ofs ?? 0} OF · ${counts.commandes_clients ?? 0} commandes`
                      : "N/A"}
                  </strong>
                  <p className="text-sm text-muted-foreground">
                    {counts
                      ? `${counts.articles ?? 0} articles · ${counts.receptions ?? 0} réceptions`
                      : "Aucun comptage disponible"}
                  </p>
                </CardContent>
              </Card>
              <Card className="border-border/70 shadow-none">
                <CardContent className="grid gap-1 px-4 py-4">
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                    Prochain geste
                  </span>
                  <strong className="text-base text-foreground">
                    {loadState === "ready"
                      ? "Lancer S+1"
                      : "Charger la source"}
                  </strong>
                  <p className="text-sm text-muted-foreground">
                    {runState === "loading"
                      ? "Un run est déjà en cours."
                      : "Le workbench S+1 sera alimenté dès que cette étape est franchie."}
                  </p>
                </CardContent>
              </Card>
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-border px-4 py-10 text-center">
              <p className="font-medium text-foreground">Aucune source chargée</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Chargez `data/` ou `Téléchargements` pour construire le contexte de lancement.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  )
}
