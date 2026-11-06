import { Activity, FileText, Gauge, Settings, Truck, type LucideIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarInput,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar"

type ViewKey = "home" | "s1" | "actions" | "reports" | "settings"
type SidebarTone = "checking" | "ready" | "error" | "idle" | "loading" | "success"

interface NavItem {
  key: ViewKey
  label: string
  hint: string
  icon: LucideIcon
}

interface AppSidebarProps {
  activeView: ViewKey
  onNavigate: (view: ViewKey) => void
  backendState: SidebarTone
  loadState: SidebarTone
  runState: SidebarTone
}

const NAV_ITEMS: NavItem[] = [
  { key: "home", label: "Home", hint: "Sources et readiness", icon: Gauge },
  { key: "s1", label: "S+1", hint: "Workbench OF", icon: Activity },
  { key: "actions", label: "Actions", hint: "Appro et kanban", icon: Truck },
  { key: "reports", label: "Reports", hint: "Exports Markdown", icon: FileText },
  { key: "settings", label: "Settings", hint: "Configuration locale", icon: Settings },
]

function getBadgeVariant(state: SidebarTone) {
  if (state === "ready" || state === "success") return "default"
  if (state === "error") return "destructive"
  return "secondary"
}

export function AppSidebar({
  activeView,
  onNavigate,
  backendState,
  loadState,
  runState,
}: AppSidebarProps) {
  return (
    <Sidebar collapsible="icon" variant="inset">
      <SidebarHeader className="gap-4 border-b border-sidebar-border/70">
        <div className="space-y-1 px-2">
          <p className="text-xs font-medium uppercase tracking-[0.24em] text-muted-foreground">
            shadcn command center
          </p>
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Ordo GUI</h1>
            <p className="text-sm text-muted-foreground">
              Faisabilité, S+1 et actions appro dans un shell unifié.
            </p>
          </div>
        </div>
        <SidebarInput placeholder="Navigation locale" />
      </SidebarHeader>

      <SidebarContent className="px-2">
        <SidebarMenu>
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon
            return (
              <SidebarMenuItem key={item.key}>
                <SidebarMenuButton
                  isActive={activeView === item.key}
                  onClick={() => onNavigate(item.key)}
                  tooltip={`${item.label} · ${item.hint}`}
                  className="h-auto items-start px-3 py-3"
                >
                  <Icon className="mt-0.5" />
                  <div className="flex min-w-0 flex-col">
                    <span>{item.label}</span>
                    <span className="truncate text-xs text-muted-foreground">
                      {item.hint}
                    </span>
                  </div>
                </SidebarMenuButton>
              </SidebarMenuItem>
            )
          })}
        </SidebarMenu>
      </SidebarContent>

      <SidebarFooter className="gap-3 border-t border-sidebar-border/70">
        <div className="grid gap-2 rounded-xl bg-sidebar-accent/60 p-3">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs uppercase tracking-[0.16em] text-muted-foreground">API</span>
            <Badge variant={getBadgeVariant(backendState)}>{backendState}</Badge>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Source</span>
            <Badge variant={getBadgeVariant(loadState)}>{loadState}</Badge>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Run S+1</span>
            <Badge variant={getBadgeVariant(runState)}>{runState}</Badge>
          </div>
        </div>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
