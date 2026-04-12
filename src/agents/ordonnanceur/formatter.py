"""Formateur de rapports pour l'Agent Ordonnanceur.

Produit des rapports textuels optimisés pour Telegram/Discord.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from .analyzer import AnalyseResult, AlerteOrdonnanceur, LineAnalysis
from .config import NotificationConfig


def format_rapport_quotidien(analyse: AnalyseResult, config: NotificationConfig) -> str:
    """Format le rapport quotidien de l'ordonnanceur."""
    e = config.use_emoji
    lines = []

    # En-tête
    lines.append(_header("ORDONNANCEUR — RAPPORT QUOTIDIEN", analyse.date_analyse, e))

    # KPIs principaux
    lines.append(_section("📊 KPIs Planning", e))
    lines.append(_kpi_line("Score", f"{analyse.score:.3f}", e))
    lines.append(_kpi_line("Taux service", f"{analyse.taux_service:.1%}", e, _service_tone(analyse.taux_service)))
    lines.append(_kpi_line("Taux ouverture", f"{analyse.taux_ouverture:.1%}", e, _ouverture_tone(analyse.taux_ouverture)))
    lines.append(_kpi_line("Déviations", str(analyse.nb_deviations), e, "warn" if analyse.nb_deviations > 3 else "ok"))
    lines.append(_kpi_line("Chgmts série", str(analyse.nb_changements_serie), e))
    lines.append(_kpi_line("OFs non planifiés", str(analyse.nb_ofs_non_planifies), e, "warn" if analyse.nb_ofs_non_planifies > 0 else "ok"))
    lines.append("")

    # Alertes consolidées (TOP 5)
    if analyse.alertes:
        lines.append(_section("🚨 Alertes", e))
        for alerte in analyse.alertes[:5]:
            lines.append(_format_alerte(alerte, e))
        if len(analyse.alertes) > 5:
            lines.append(f"  ... et {len(analyse.alertes) - 5} autre(s)")
        lines.append("")

    # Charge par ligne par jour
    lines.append(_section("📅 Charge par ligne", e))
    for la in analyse.lignes:
        if la.total_ofs == 0:
            continue
        lines.append(f"  {'🏭' if e else '>>'} {la.line}: {la.total_ofs} OFs, {la.total_hours}h")
        for day, hours in sorted(la.charge_by_day.items()):
            bar = _bar(hours, 14.0)
            lines.append(f"    {day}: {hours:.1f}h {bar}")
    lines.append("")

    # OFs non planifiés (top 5)
    if analyse.ofs_non_planifies:
        lines.append(_section("❌ OFs non planifiés (top)", e))
        for row in analyse.ofs_non_planifies[:5]:
            cause = row.get("cause", "?")[:60]
            lines.append(f"  • {row.get('of', '?')} ({row.get('article', '?')}) — {row.get('ligne', '?')}")
            lines.append(f"    Échéance: {row.get('date_echeance', '?')} | {row.get('charge_h', 0)}h | {cause}")
        lines.append("")

    # Messages réordonnancement critiques
    msgs_critiques = [m for m in analyse.messages_reordonnancement if m.priorite == 1]
    if msgs_critiques:
        lines.append(_section("⏰ OFs critiques", e))
        for m in msgs_critiques[:5]:
            icon = _msg_icon(m.type, e)
            lines.append(f"  {icon} {m.num_of} ({m.article}) — {m.type}")
            lines.append(f"    {m.message}")
            lines.append(f"    → {m.action_recommandee}")
        lines.append("")

    # Réceptions en retard
    recep_critiques = [r for r in analyse.receptions_en_retard if r.niveau_risque == "CRITIQUE"]
    if recep_critiques:
        lines.append(_section("📦 Réceptions en retard critique", e))
        for r in recep_critiques[:5]:
            lines.append(f"  {'🔴' if e else '[!]'} {r.article} — {r.fournisseur} ({r.jours_retard}j retard)")
            lines.append(f"    {len(r.ofs_bloques)} OF(s) impacté(s)")
        lines.append("")

    # Goulots saturés
    goulots_satures = [g for g in analyse.alertes_goulots if g.statut == "SATURE"]
    if goulots_satures:
        lines.append(_section("🏭 Postes saturés", e))
        for g in goulots_satures[:5]:
            lines.append(f"  {'⚠️' if e else '[!]'} {g.poste} ({g.semaine}) — {g.taux_charge:.0%}")
            lines.append(f"    {g.suggestion}")
        lines.append("")

    # Commandes en retard (si > 0)
    if analyse.kpis_service and analyse.kpis_service.nb_commandes_en_retard > 0:
        lines.append(_section("📋 Commandes en retard", e))
        kpis = analyse.kpis_service
        lines.append(f"  Total: {kpis.nb_commandes_en_retard} sur {kpis.nb_commandes_total} commandes")
        for cmd in kpis.commandes_en_retard[:5]:
            lines.append(f"  • {cmd}")
        if len(kpis.commandes_en_retard) > 5:
            lines.append(f"  ... et {len(kpis.commandes_en_retard) - 5} autre(s)")
        lines.append("")

    # Résumé exécution scheduler
    lines.append(_section("⚙️ Scheduler", e))
    for la in analyse.lignes:
        lines.append(f"  {la.line}: {la.total_ofs} OFs planifiés, {la.changements_serie} changements série")
    lines.append("")

    # Conclusion
    lines.append(_conclusion(analyse, e))

    return "\n".join(lines)


def format_rapport_hebdo(analyse: AnalyseResult, config: NotificationConfig) -> str:
    """Format le rapport hebdomadaire (vendredi)."""
    e = config.use_emoji
    lines = []

    lines.append(_header("ORDONNANCEUR — BILAN HEBDOMADAIRE", analyse.date_analyse, e))

    # KPIs synthèse
    lines.append(_section("📊 Synthèse semaine", e))
    lines.append(f"  Score planning: {analyse.score:.3f}")
    lines.append(f"  Taux service: {analyse.taux_service:.1%}")
    lines.append(f"  Taux ouverture: {analyse.taux_ouverture:.1%}")
    lines.append(f"  Déviations totales: {analyse.nb_deviations}")
    lines.append(f"  OFs non planifiés: {analyse.nb_ofs_non_planifies}")
    if analyse.kpis_service:
        kpis = analyse.kpis_service
        lines.append(f"  Commandes en retard: {kpis.nb_commandes_en_retard}/{kpis.nb_commandes_total}")
        lines.append(f"  OFs affermis actifs: {kpis.ofs_affermis_actifs}")
        lines.append(f"  OFs suggérés actifs: {kpis.ofs_suggeres_actifs}")
    lines.append("")

    # Top alertes de la semaine
    if analyse.alertes:
        lines.append(_section("🚨 Alertes de la semaine", e))
        nb_critiques = sum(1 for a in analyse.alertes if a.niveau == "CRITIQUE")
        nb_attention = sum(1 for a in analyse.alertes if a.niveau == "ATTENTION")
        lines.append(f"  CRITIQUE: {nb_critiques} | ATTENTION: {nb_attention}")
        for alerte in analyse.alertes[:8]:
            lines.append(_format_alerte(alerte, e))
        lines.append("")

    # Performance par ligne
    lines.append(_section("🏭 Performance par ligne", e))
    for la in analyse.lignes:
        if la.total_ofs == 0:
            lines.append(f"  {la.line}: inactive")
            continue
        avg_daily = la.total_hours / max(1, len(la.charge_by_day))
        lines.append(f"  {la.line}: {la.total_ofs} OFs, {la.total_hours}h, moy {avg_daily:.1f}h/jour, {la.changements_serie} chgmts")
    lines.append("")

    # Goulots récurrents
    if analyse.alertes_goulots:
        lines.append(_section("🔧 Postes sous tension", e))
        for g in analyse.alertes_goulots[:5]:
            statut_icon = {"SATURE": "🔴", "TENSION": "🟡", "SOUS_CHARGE": "🟢"}.get(g.statut, "⚪")
            if not e:
                statut_icon = {"SATURE": "[!!!]", "TENSION": "[!!]", "SOUS_CHARGE": "[~]"}.get(g.statut, "[-]")
            lines.append(f"  {statut_icon} {g.poste} ({g.semaine}) — {g.taux_charge:.0%} | {g.suggestion}")
        lines.append("")

    # KPIs par client (si disponible)
    if analyse.kpis_service and analyse.kpis_service.kpis_par_client:
        lines.append(_section("👥 Taux de service par client", e))
        for ck in sorted(analyse.kpis_service.kpis_par_client, key=lambda k: k.taux_service)[:8]:
            icon = "🟢" if ck.taux_service >= 0.9 else ("🟡" if ck.taux_service >= 0.75 else "🔴")
            if not e:
                icon = "[ok]" if ck.taux_service >= 0.9 else ("[!!]" if ck.taux_service >= 0.75 else "[!]")
            lines.append(f"  {icon} {ck.nom_client}: {ck.taux_service:.0%} ({ck.nb_commandes_servies}/{ck.nb_commandes_total})")
        lines.append("")

    lines.append(_conclusion(analyse, e))

    return "\n".join(lines)


def format_alerte_unique(alerte: AlerteOrdonnanceur, config: NotificationConfig) -> str:
    """Format une alerte unique pour notification temps réel."""
    e = config.use_emoji
    lines = []

    niveau_icon = {"CRITIQUE": "🚨", "ATTENTION": "⚠️", "INFO": "ℹ️"}.get(alerte.niveau, "❓")
    if not e:
        niveau_icon = {"CRITIQUE": "[CRITIQUE]", "ATTENTION": "[ATTENTION]", "INFO": "[INFO]"}.get(alerte.niveau, "[?]")

    lines.append(f"{niveau_icon} ORDONNANCEUR — {alerte.niveau}")
    lines.append(f"📂 {alerte.categorie}")
    lines.append(f"📝 {alerte.message}")
    lines.append(f"👉 {alerte.action}")

    if alerte.details:
        lines.append("")
        lines.append("Détails:")
        for key, values in alerte.details.items():
            if isinstance(values, list):
                for v in values[:3]:
                    if isinstance(v, dict):
                        detail = " | ".join(f"{k}: {val}" for k, val in v.items())
                        lines.append(f"  • {detail}")
                    else:
                        lines.append(f"  • {v}")

    return "\n".join(lines)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _header(title: str, d: date, e: bool) -> str:
    sep = "═" * 40
    cal_icon = "📅" if e else ""
    return f"\n{sep}\n{cal_icon} {title} — {d.strftime('%A %d/%m/%Y')}\n{sep}"


def _section(title: str, e: bool) -> str:
    return f"\n{'─' * 30}\n{title}\n{'─' * 30}"


def _kpi_line(label: str, value: str, e: bool, tone: str = "neutral") -> str:
    if e:
        icons = {"ok": "✅", "warn": "⚠️", "crit": "🔴", "neutral": "  "}
        icon = icons.get(tone, "  ")
        return f"  {icon} {label}: {value}"
    return f"  [{tone.upper():>4}] {label}: {value}"


def _format_alerte(a: AlerteOrdonnanceur, e: bool) -> str:
    if e:
        icons = {"CRITIQUE": "🔴", "ATTENTION": "🟡", "INFO": "🔵"}
        icon = icons.get(a.niveau, "⚪")
        return f"  {icon} [{a.categorie}] {a.message}\n    → {a.action}"
    return f"  [{a.niveau}] {a.categorie}: {a.message}\n    → {a.action}"


def _service_tone(taux: float) -> str:
    if taux >= 0.90:
        return "ok"
    if taux >= 0.75:
        return "warn"
    return "crit"


def _ouverture_tone(taux: float) -> str:
    if 0.50 <= taux <= 0.90:
        return "ok"
    if taux < 0.50:
        return "warn"
    return "crit"


def _bar(value: float, max_value: float, width: int = 10) -> str:
    filled = int((value / max_value) * width) if max_value > 0 else 0
    filled = min(filled, width)
    return "█" * filled + "░" * (width - filled)


def _msg_icon(msg_type: str, e: bool) -> str:
    if not e:
        return f"[{msg_type}]"
    return {
        "RETARD": "🔴",
        "RETARD_IMMINENT": "🟠",
        "URGENCE": "🟡",
        "DEBLOCAGE": "🔵",
    }.get(msg_type, "⚪")


def _conclusion(analyse: AnalyseResult, e: bool) -> str:
    """Génère une conclusion synthétique."""
    nb_crit = sum(1 for a in analyse.alertes if a.niveau == "CRITIQUE")
    nb_warn = sum(1 for a in analyse.alertes if a.niveau == "ATTENTION")

    if nb_crit > 0:
        conclusion = f"{'🚨' if e else '[!!!]'} {nb_crit} alerte(s) CRITIQUE(s) — action requise"
    elif nb_warn > 0:
        conclusion = f"{'⚠️' if e else '[!!]'} {nb_warn} attention(s) — surveillance recommandée"
    else:
        conclusion = f"{'✅' if e else '[OK]'} Situation sous contrôle"

    return f"\n{'═' * 40}\n{conclusion}\n{'═' * 40}"
