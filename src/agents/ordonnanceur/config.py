"""Configuration de l'Agent Ordonnanceur.

Tous les seuils, horizons et paramètres ajustables en un seul endroit.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class SchedulerConfig:
    """Paramètres du scheduler."""
    planning_workdays: int = 5
    demand_calendar_days: int = 15
    weights_path: str = "config/weights.json"
    output_dir: str = "outputs"
    lines_config: Optional[list[str]] = None  # None = auto-detect all lines


@dataclass
class AnalysisConfig:
    """Paramètres d'analyse post-scheduler."""
    num_weeks_heatmap: int = 4
    capacite_nominale_poste: float = 35.0  # heures/semaine
    seuil_taux_service_alerte: float = 0.85  # < 85% = alerte
    seuil_taux_ouverture_min: float = 0.50  # < 50% = sous-charge
    seuil_taux_ouverture_max: float = 0.90  # > 90% = saturation
    seuil_deviations_alerte: int = 3  # > 3 déviations = alerte
    max_ofs_non_planifies_report: int = 15
    max_commandes_retard_report: int = 10
    max_alertes_report: int = 20


@dataclass
class HeartbeatConfig:
    """Paramètres du heartbeat (fréquence d'exécution)."""
    # Cron expressions (non utilisées directement, info pour le cron Hermes)
    cron_quotidien: str = "0 7 * * 1-5"  # 7h00 jours ouvrés
    cron_hebdo_vendredi: str = "0 17 * * 5"  # 17h00 vendredi


@dataclass
class NotificationConfig:
    """Paramètres de notification."""
    # Niveaux de sévérité pour les notifications
    notify_on_critical: bool = True   # Taux service < seuil, OFs bloqués
    notify_on_warning: bool = True    # Déviations, sous-charge
    notify_on_info: bool = False      # RAS, routine
    # Format de sortie
    use_emoji: bool = True
    max_message_length: int = 8000  # Limite Discord (Telegram = 4096)


@dataclass
class AgentConfig:
    """Configuration complète de l'Agent Ordonnanceur."""
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    heartbeat: HeartbeatConfig = field(default_factory=HeartbeatConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)

    @classmethod
    def from_yaml(cls, path: str = "config/ordonnanceur.yaml") -> "AgentConfig":
        """Charge la config depuis un YAML (fallback sur les defaults)."""
        import yaml
        p = Path(path)
        if not p.exists():
            return cls()
        with open(p, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        cfg = cls()
        if "scheduler" in raw:
            cfg.scheduler = SchedulerConfig(**raw["scheduler"])
        if "analysis" in raw:
            cfg.analysis = AnalysisConfig(**raw["analysis"])
        if "heartbeat" in raw:
            cfg.heartbeat = HeartbeatConfig(**raw["heartbeat"])
        if "notification" in raw:
            cfg.notification = NotificationConfig(**raw["notification"])
        return cfg
