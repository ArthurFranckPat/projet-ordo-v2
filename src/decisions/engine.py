"""Moteur de décision pour l'ordonnancement."""

from datetime import date
from typing import Dict, List, Optional

from .smart_rule import SmartDecisionRule
from .models import DecisionResult, DecisionContext, DecisionAction
from .persistence import DecisionPersistence
from ..models.of import OF
from ..models.besoin_client import BesoinClient


class DecisionEngine:
    """Orchestrateur de l'évaluation des décisions métier."""

    def __init__(
        self,
        config_path: str = "config/decisions.yaml",
        persistence_enabled: bool = True
    ):
        """Initialise le moteur de décision.

        Parameters
        ----------
        config_path : str
            Chemin vers le fichier de configuration YAML
        persistence_enabled : bool
            Active la persistance des décisions en JSON
        """
        self.smart_rule = SmartDecisionRule(config_path)
        if persistence_enabled:
            self.persistence = DecisionPersistence(
                file_path="data/decisions_history.json",
                max_entries=10000
            )
        else:
            self.persistence = None
        self.persistence_enabled = persistence_enabled

    def evaluate_pre_allocation(
        self,
        of: OF,
        initial_stock: Dict[str, int],
        competing_ofs: Optional[List[OF]] = None,
        commande: Optional[BesoinClient] = None
    ) -> DecisionResult:
        """Évalue un OF avant allocation virtuelle.

        Parameters
        ----------
        of : OF
            OF à évaluer
        initial_stock : Dict[str, int]
            Stock initial par article
        competing_ofs : Optional[List[OF]]
            Liste des OFs en concurrence
        commande : Optional[BesoinClient]
            Commande associée

        Returns
        -------
        DecisionResult
            Décision avec action possiblement ACCEPT_PARTIAL
        """
        context = DecisionContext(
            of=of,
            commande=commande,
            initial_stock=initial_stock,
            allocated_stock={},
            remaining_stock=initial_stock.copy(),
            competing_ofs=competing_ofs or [],
            current_date=date.today()
        )

        decision = self.smart_rule.evaluate(context)

        # Persister si activé
        if self.persistence:
            self.persistence.save_decision(
                of_num=of.num_of,
                decision=decision,
                allocation_phase="pre"
            )

        return decision

    def evaluate_post_allocation(
        self,
        of: OF,
        allocation_result,
        commande: Optional[BesoinClient] = None,
        allocated_stock: Optional[Dict[str, int]] = None
    ) -> DecisionResult:
        """Évalue un OF après allocation virtuelle (si échec).

        Parameters
        ----------
        of : OF
            OF à évaluer
        allocation_result
            Résultat de l'allocation
        commande : Optional[BesoinClient]
            Commande associée
        allocated_stock : Optional[Dict[str, int]]
            Stock alloué

        Returns
        -------
        DecisionResult
            Décision avec action DEFER, REJECT ou ACCEPT_AS_IS
        """
        context = DecisionContext(
            of=of,
            commande=commande,
            feasibility_result=allocation_result.feasibility_result,
            initial_stock={},
            allocated_stock=allocated_stock or {},
            remaining_stock={},
            competing_ofs=[],
            current_date=date.today()
        )

        decision = self.smart_rule.evaluate(context)

        # Persister si activé
        if self.persistence:
            self.persistence.save_decision(
                of_num=of.num_of,
                decision=decision,
                allocation_phase="post"
            )

        return decision
