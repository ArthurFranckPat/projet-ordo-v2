"""Agent Ordonnanceur — Employé autonome de planification production.

Cet agent est un "employé" autonome qui :
1. Se réveille sur un heartbeat (cron)
2. Charge les données depuis les CSV
3. Exécute le scheduler (run_schedule)
4. Analyse les résultats avec les outils agent existants
5. Génère un rapport structuré
6. Notifie via le canal configuré (stdout → Telegram/Discord)

Missions couvertes :
- Planification jour/jour des lignes de production
- Vérification de faisabilité des OF
- Calcul et suivi des KPIs (taux service, taux ouverture)
- Détection des goulots, retards, déviations
- Génération des rapports quotidien et hebdomadaire
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from ...loaders.data_loader import DataLoader
from ...scheduler import run_schedule
from .analyzer import analyze_scheduler_result, AnalyseResult
from .formatter import (
    format_rapport_quotidien,
    format_rapport_hebdo,
    format_alerte_unique,
)
from .config import AgentConfig


@dataclass
class AgentStatus:
    """État d'exécution de l'agent."""
    success: bool
    mode: str
    duree_secondes: float
    erreurs: list[str]
    fichiers_generes: list[str]


class AgentOrdonnanceur:
    """Agent Ordonnanceur — Employé autonome de planification production.

    Usage:
        agent = AgentOrdonnanceur(data_dir="data")
        status = agent.run(mode="quotidien")
        # Le rapport est écrit sur stdout
    """

    def __init__(
        self,
        data_dir: str = "data",
        config: Optional[AgentConfig] = None,
        reference_date: Optional[date] = None,
    ):
        self.data_dir = data_dir
        self.config = config or AgentConfig()
        self.reference_date = reference_date or date.today()
        self._loader: Optional[DataLoader] = None
        self._derniere_analyse: Optional[AnalyseResult] = None

    @property
    def loader(self) -> DataLoader:
        """Lazy-load du DataLoader."""
        if self._loader is None:
            self._loader = DataLoader(self.data_dir)
            self._loader.load_all()
        return self._loader

    def run(self, mode: str = "quotidien") -> AgentStatus:
        """Point d'entrée principal de l'agent.

        Parameters
        ----------
        mode : str
            "quotidien"  → rapport complet (scheduler + outils + alertes)
            "hebdo"      → bilan hebdomadaire (vendredi)
            "scheduler"  → scheduler uniquement (pas d'analyse agent)
            "analyse"    → analyse uniquement (réutilise les derniers outputs)
        """
        import time
        start = time.time()
        erreurs = []
        fichiers = []

        try:
            if mode == "analyse":
                analyse = self._run_analyse_only()
            else:
                analyse = self._run_full(mode)

            self._derniere_analyse = analyse

            # Formatage du rapport
            cfg = self.config.notification
            if mode == "hebdo":
                rapport = format_rapport_hebdo(analyse, cfg)
            else:
                rapport = format_rapport_quotidien(analyse, cfg)

            # Tronquer si trop long pour Telegram
            if len(rapport) > cfg.max_message_length:
                rapport = rapport[:cfg.max_message_length - 50] + "\n\n[...] rapport tronqué"

            # Écriture sur stdout
            print(rapport)

            # Écriture du rapport dans un fichier (audit trail)
            output_dir = Path(self.config.scheduler.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            date_str = self.reference_date.strftime("%Y-%m-%d")
            rapport_path = output_dir / f"rapport_ordonnanceur_{mode}_{date_str}.txt"
            rapport_path.write_text(rapport, encoding="utf-8")
            fichiers.append(str(rapport_path))

            # Sauvegarde JSON de l'analyse (machine-readable)
            json_path = output_dir / f"analyse_ordonnanceur_{date_str}.json"
            self._save_analyse_json(analyse, json_path)
            fichiers.append(str(json_path))

        except Exception as exc:
            erreurs.append(str(exc))
            print(f"ERREUR AGENT ORDONNANCEUR: {exc}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)

        duree = time.time() - start
        return AgentStatus(
            success=len(erreurs) == 0,
            mode=mode,
            duree_secondes=round(duree, 2),
            erreurs=erreurs,
            fichiers_generes=fichiers,
        )

    def _run_full(self, mode: str) -> AnalyseResult:
        """Exécution complète : scheduler + analyse."""
        cfg = self.config.scheduler

        # 1. Charger les données
        loader = self.loader

        # 2. Exécuter le scheduler
        result = run_schedule(
            loader,
            lines_config=cfg.lines_config,
            reference_date=self.reference_date,
            planning_workdays=cfg.planning_workdays,
            demand_calendar_days=cfg.demand_calendar_days,
            output_dir=cfg.output_dir,
            weights_path=cfg.weights_path,
        )

        # 3. Analyser les résultats
        analyse = analyze_scheduler_result(
            result=result,
            loader=loader,
            config=self.config.analysis,
            reference_date=self.reference_date,
            mode=mode,
        )

        return analyse

    def _run_analyse_only(self) -> AnalyseResult:
        """Analyse sans ré-exécuter le scheduler (lit les outputs existants)."""
        output_dir = Path(self.config.scheduler.output_dir)

        # Charger les KPIs précédents
        kpis_path = output_dir / "kpis.json"
        if not kpis_path.exists():
            raise FileNotFoundError(
                f"Aucun résultat scheduler trouvé dans {output_dir}. "
                "Exécutez d'abord le mode 'quotidien' ou 'scheduler'."
            )

        with open(kpis_path, "r", encoding="utf-8") as f:
            kpis = json.load(f)

        # Charger les alertes
        alertes_path = output_dir / "alertes.txt"
        alertes = []
        if alertes_path.exists():
            alertes = alertes_path.read_text(encoding="utf-8").strip().split("\n")
            alertes = [a for a in alertes if a]

        # Charger les OFs non planifiés
        unscheduled = []
        unscheduled_path = output_dir / "ofs_non_faisables.csv"
        if unscheduled_path.exists():
            import csv
            with open(unscheduled_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                unscheduled = list(reader)

        # Charger les order rows
        order_rows = []
        order_path = output_dir / "lignes_commande_statut.csv"
        if order_path.exists():
            import csv
            with open(order_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                order_rows = list(reader)

        # Charger stock BDH projeté
        stock_bdh = []
        stock_path = output_dir / "stock_BDH_projete.csv"
        if stock_path.exists():
            import csv
            with open(stock_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                stock_bdh = list(reader)

        # Construire un SchedulerResult minimal pour l'analyse
        from ...scheduler.models import SchedulerResult
        result = SchedulerResult(
            score=kpis.get("score", 0.0),
            taux_service=kpis.get("taux_service", 0.0),
            taux_ouverture=kpis.get("taux_ouverture", 0.0),
            nb_deviations=kpis.get("nb_deviations", 0),
            nb_jit=kpis.get("nb_jit", 0),
            nb_changements_serie=0,
            plannings={},
            stock_projection=stock_bdh,
            alerts=alertes,
            weights=kpis.get("weights", {}),
            unscheduled_rows=unscheduled,
            order_rows=order_rows,
        )

        # Analyser (les outils agent tournent quand même)
        return analyze_scheduler_result(
            result=result,
            loader=self.loader,
            config=self.config.analysis,
            reference_date=self.reference_date,
            mode="analyse",
        )

    def _save_analyse_json(self, analyse: AnalyseResult, path: Path) -> None:
        """Sauvegarde l'analyse en JSON (machine-readable)."""
        data = {
            "date_analyse": analyse.date_analyse.isoformat(),
            "mode": analyse.mode,
            "kpis": {
                "score": analyse.score,
                "taux_service": analyse.taux_service,
                "taux_ouverture": analyse.taux_ouverture,
                "nb_deviations": analyse.nb_deviations,
                "nb_jit": analyse.nb_jit,
                "nb_changements_serie": analyse.nb_changements_serie,
                "nb_ofs_non_planifies": analyse.nb_ofs_non_planifies,
            },
            "lignes": [
                {
                    "line": la.line,
                    "total_ofs": la.total_ofs,
                    "total_hours": la.total_hours,
                    "changements_serie": la.changements_serie,
                    "charge_by_day": la.charge_by_day,
                }
                for la in analyse.lignes
            ],
            "alertes": [
                {
                    "niveau": a.niveau,
                    "categorie": a.categorie,
                    "message": a.message,
                    "action": a.action,
                }
                for a in analyse.alertes
            ],
            "kpis_service": {
                "taux_service_global": analyse.kpis_service.taux_service_global,
                "nb_commandes_en_retard": analyse.kpis_service.nb_commandes_en_retard,
                "nb_commandes_total": analyse.kpis_service.nb_commandes_total,
                "ofs_affermis_actifs": analyse.kpis_service.ofs_affermis_actifs,
                "ofs_suggeres_actifs": analyse.kpis_service.ofs_suggeres_actifs,
            } if analyse.kpis_service else None,
            "nb_messages_critiques": sum(
                1 for m in analyse.messages_reordonnancement if m.priorite == 1
            ),
            "nb_receptions_retard_critique": sum(
                1 for r in analyse.receptions_en_retard if r.niveau_risque == "CRITIQUE"
            ),
            "nb_goulots_satures": sum(
                1 for g in analyse.alertes_goulots if g.statut == "SATURE"
            ),
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
