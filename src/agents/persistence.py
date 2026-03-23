"""Persistance des décisions métier en JSON."""

import json
import os
from typing import Dict, List, Any

from .models import AgentDecision


class DecisionPersistence:
    """Gestion de la persistance des décisions."""

    def __init__(self, file_path: str, max_entries: int = 10000):
        """Initialise la persistance.

        Parameters
        ----------
        file_path : str
            Chemin vers le fichier JSON d'historique
        max_entries : int
            Nombre maximum d'entrées avant rotation
        """
        self.file_path = file_path
        self.max_entries = max_entries

    def save_decision(
        self,
        of_num: str,
        decision: AgentDecision,
        allocation_phase: str
    ):
        """Sauvegarde une décision dans l'historique.

        Parameters
        ----------
        of_num : str
            Numéro de l'OF
        decision : AgentDecision
            Décision à sauvegarder
        allocation_phase : str
            Phase d'allocation ("pre" ou "post")
        """
        entry = {
            "timestamp": decision.timestamp.isoformat(),
            "of_num": of_num,
            "phase": allocation_phase,
            "action": decision.action.value,
            "reason": decision.reason,
            "modified_quantity": decision.modified_quantity,
            "metadata": decision.metadata
        }

        # Charger l'historique existant
        history = self._load_history()

        # Ajouter la nouvelle entrée
        history.append(entry)

        # Rotation si nécessaire
        if len(history) > self.max_entries:
            history = history[-self.max_entries:]

        # Sauvegarder
        self._save_history(history)

    def _load_history(self) -> List[Dict]:
        """Charge l'historique depuis le fichier.

        Returns
        -------
        List[Dict]
            Historique des décisions
        """
        if not os.path.exists(self.file_path):
            return []

        with open(self.file_path, 'r') as f:
            content = f.read().strip()
            if not content:
                return []
            return json.loads(content)

    def _save_history(self, history: List[Dict]):
        """Sauvegarde l'historique dans le fichier.

        Parameters
        ----------
        history : List[Dict]
            Historique à sauvegarder
        """
        # Créer le répertoire si nécessaire
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)

        with open(self.file_path, 'w') as f:
            json.dump(history, f, indent=2)
