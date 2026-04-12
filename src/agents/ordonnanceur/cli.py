"""CLI pour l'Agent Ordonnanceur.

Usage:
    python -m src.agents.ordonnanceur.cli                    # Rapport quotidien
    python -m src.agents.ordonnanceur.cli --mode hebdo       # Bilan hebdo
    python -m src.agents.ordonnanceur.cli --mode scheduler   # Scheduler seul
    python -m src.agents.ordonnanceur.cli --mode analyse     # Analyse seule
    python -m src.agents.ordonnanceur.cli --date 2026-04-14  # Date spécifique
"""

import argparse
import sys
from datetime import datetime

from .agent import AgentOrdonnanceur
from .config import AgentConfig


def main():
    parser = argparse.ArgumentParser(
        description="Agent Ordonnanceur — Planification autonome de la production"
    )
    parser.add_argument(
        "--mode",
        choices=["quotidien", "hebdo", "scheduler", "analyse"],
        default="quotidien",
        help="Mode d'exécution (défaut: quotidien)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="data",
        help="Répertoire des données CSV (défaut: data)",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Date de référence au format YYYY-MM-DD (défaut: aujourd'hui)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Chemin vers le fichier de config YAML",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="outputs",
        help="Répertoire de sortie (défaut: outputs)",
    )
    parser.add_argument(
        "--no-emoji",
        action="store_true",
        help="Désactiver les emojis dans le rapport",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Sortie JSON au lieu du texte formaté",
    )

    args = parser.parse_args()

    # Résoudre la date
    reference_date = None
    if args.date:
        reference_date = datetime.strptime(args.date, "%Y-%m-%d").date()

    # Charger la config
    if args.config:
        config = AgentConfig.from_yaml(args.config)
    else:
        config = AgentConfig()

    # Overrides CLI
    config.scheduler.output_dir = args.output_dir
    if args.no_emoji:
        config.notification.use_emoji = False

    # Créer et exécuter l'agent
    agent = AgentOrdonnanceur(
        data_dir=args.data_dir,
        config=config,
        reference_date=reference_date,
    )

    status = agent.run(mode=args.mode)

    if args.json_output:
        import json
        print(json.dumps({
            "success": status.success,
            "mode": status.mode,
            "duree_secondes": status.duree_secondes,
            "erreurs": status.erreurs,
            "fichiers_generes": status.fichiers_generes,
        }, indent=2, ensure_ascii=False))

    sys.exit(0 if status.success else 1)


if __name__ == "__main__":
    main()
