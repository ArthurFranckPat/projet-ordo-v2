"""Moteur de décision pour l'ordonnancement."""

from datetime import date
from typing import Dict, List, Optional, TYPE_CHECKING

from .smart_rule import SmartDecisionRule
from .models import DecisionResult, DecisionContext, DecisionAction
from .persistence import DecisionPersistence
from ..models.of import OF
from ..models.besoin_client import BesoinClient

if TYPE_CHECKING:
    from ..loaders.data_loader import DataLoader
    from .llm.llm_decision_rule import LLMBasedDecisionRule


class DecisionEngine:
    """Orchestrateur de l'évaluation des décisions métier.

    Peut fonctionner en mode classique (règles statiques) ou en mode LLM
    pour des décisions plus nuancées.
    """

    def __init__(
        self,
        config_path: str = "config/decisions.yaml",
        persistence_enabled: bool = True,
        use_llm: bool = False,
        llm_client=None,
        loader: Optional["DataLoader"] = None
    ):
        """Initialise le moteur de décision.

        Parameters
        ----------
        config_path : str
            Chemin vers le fichier de configuration YAML
        persistence_enabled : bool
            Active la persistance des décisions en JSON
        use_llm : bool
            Active le mode LLM pour les décisions (défaut: False)
        llm_client : BaseLLMClient, optional
            Client LLM (requis si use_llm=True)
        loader : DataLoader, optional
            DataLoader avec accès aux données (requis si use_llm=True)
        """
        self.use_llm = use_llm
        self.loader = loader
        self.config_path = config_path

        if use_llm:
            if llm_client is None:
                raise ValueError("llm_client est requis en mode LLM")
            if loader is None:
                raise ValueError("loader est requis en mode LLM")

            # Importer ici pour éviter les imports circulaires
            from .llm.llm_decision_rule import LLMBasedDecisionRule

            self.llm_rule = LLMBasedDecisionRule(
                llm_client=llm_client,
                config_path=config_path
            )
            self.smart_rule = None
        else:
            self.smart_rule = SmartDecisionRule(config_path)
            self.llm_rule = None

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
            Stock initial par article (non utilisé en mode LLM)
        competing_ofs : Optional[List[OF]]
            Liste des OFs en concurrence
        commande : Optional[BesoinClient]
            Commande associée

        Returns
        -------
        DecisionResult
            Décision avec action possiblement ACCEPT_PARTIAL
        """
        if self.use_llm:
            # Mode LLM : le contexte est construit par LLMContextBuilder
            decision = self.llm_rule.evaluate(
                of=of,
                commande=commande,
                loader=self.loader,
                competing_ofs=competing_ofs,
                current_date=date.today()
            )
        else:
            # Mode classique : utilise DecisionContext
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
            Stock alloué (non utilisé en mode LLM)

        Returns
        -------
        DecisionResult
            Décision avec action DEFER, REJECT ou ACCEPT_AS_IS
        """
        if self.use_llm:
            # Mode LLM : réévalue avec le même contexte
            # (le LLM a déjà une vision complète via allocations.csv)
            decision = self.llm_rule.evaluate(
                of=of,
                commande=commande,
                loader=self.loader,
                competing_ofs=None,
                current_date=date.today()
            )
        else:
            # Mode classique : utilise DecisionContext
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
