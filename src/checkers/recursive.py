"""Recursive Checker - Algorithme de vérification récursive des nomenclatures."""

from typing import Optional

from .base import BaseChecker, FeasibilityResult
from ..models.nomenclature import Nomenclature
from ..models.of import OF
from ..models.commande_client import CommandeClient


class RecursiveChecker(BaseChecker):
    """Checker avec vérification récursive des nomenclatures.

    Ce checker vérifie récursivement tous les niveaux de nomenclature :
    - Si un composant est ACHAT → vérifier le stock
    - Si un composant est FABRIQUÉ → vérifier récursivement sa nomenclature

    Attributes
    ----------
    data_loader : DataLoader
        Loader de données
    use_receptions : bool
        Si True, utilise les réceptions fournisseurs dans le calcul du stock
    check_date : Optional[date]
        Date de vérification (pour filtrer les réceptions)
    stock_state : Optional[StockState]
        État du stock virtuel pour allocation (None = stock réel)
    """

    def __init__(self, data_loader, use_receptions: bool = False, check_date: Optional = None, stock_state: Optional["StockState"] = None):
        """Initialise le checker récursif.

        Parameters
        ----------
        data_loader : DataLoader
            Loader de données
        use_receptions : bool
            Si True, utilise les réceptions fournisseurs
        check_date : Optional[date]
            Date de vérification (None = aujourd'hui)
        stock_state : Optional[StockState]
            État du stock virtuel pour allocation (None = stock réel)
        """
        super().__init__(data_loader)
        self.use_receptions = use_receptions
        self.check_date = check_date
        self.stock_state = stock_state

    def check_of(self, of: OF) -> FeasibilityResult:
        """Vérifie la faisabilité d'un OF avec récursion.

        Parameters
        ----------
        of : OF
            Ordre de fabrication à vérifier

        Returns
        -------
        FeasibilityResult
            Résultat de la vérification
        """
        # L'OF parent est FERME si statut = 1
        of_est_ferme = (of.statut_num == 1)

        return self._check_article_recursive(
            article=of.article,
            qte_besoin=of.qte_restante,
            date_besoin=of.date_fin,
            depth=0,
            of_parent_est_ferme=of_est_ferme,
            num_of_parent=of.num_of,
        )

    def check_commande(self, commande: CommandeClient) -> FeasibilityResult:
        """Vérifie la faisabilité d'une commande client avec récursion.

        Pour les commandes MTS avec OF lié, vérifie l'OF associé.
        Pour toutes les commandes, tient compte des allocations existantes.

        Parameters
        ----------
        commande : CommandeClient
            Commande client à vérifier

        Returns
        -------
        FeasibilityResult
            Résultat de la vérification
        """
        result = FeasibilityResult(feasible=True, depth=0)

        # Cas 1 : Commande MTS avec OF lié
        if commande.is_mts() and commande.of_contremarque:
            of = self.data_loader.get_of_by_num(commande.of_contremarque)
            if of:
                # Vérifier l'OF lié
                return self.check_of(of)
            else:
                result.add_alert(f"OF {commande.of_contremarque} introuvable pour la commande MTS")
                result.feasible = False
                return result

        # Cas 2 : Vérifier si la commande a des allocations
        allocations = self.data_loader.get_allocations_of(commande.num_commande)

        if allocations:
            # La commande a des allocations → les utiliser comme référence
            # Traiter comme si of_parent_est_ferme=True (composants déjà alloués)
            return self._check_article_recursive(
                article=commande.article,
                qte_besoin=commande.qte_restante,
                date_besoin=commande.date_expedition_demandee,
                depth=0,
                of_parent_est_ferme=True,  # Composants déjà alloués
                num_of_parent=commande.num_commande,  # Utiliser le numéro de commande
            )

        # Cas 3 : Pas d'allocations connues → vérification standard
        return self._check_article_recursive(
            article=commande.article,
            qte_besoin=commande.qte_restante,
            date_besoin=commande.date_expedition_demandee,
            depth=0,
            of_parent_est_ferme=False,
            num_of_parent=None,
        )

    def _check_article_recursive(
        self,
        article: str,
        qte_besoin: int,
        date_besoin,
        depth: int,
        of_parent_est_ferme: bool = False,
        num_of_parent: Optional[str] = None,
    ) -> FeasibilityResult:
        """Vérifie récursivement la faisabilité pour un article.

        Parameters
        ----------
        article : str
            Code de l'article à vérifier
        qte_besoin : int
            Quantité nécessaire
        date_besoin : date
            Date de besoin
        depth : int
            Profondeur de récursion actuelle
        of_parent_est_ferme : bool
            True si l'OF parent est FERME (composants déjà alloués)
        num_of_parent : Optional[str]
            Numéro de l'OF parent pour vérifier les allocations

        Returns
        -------
        FeasibilityResult
            Résultat de la vérification
        """
        result = FeasibilityResult(feasible=True, depth=depth)

        # Récupérer la nomenclature de l'article
        nomenclature = self.data_loader.get_nomenclature(article)

        if nomenclature is None:
            # Nomenclature non disponible
            result.add_alert(f"Nomenclature non disponible pour l'article {article}")
            return result

        if not nomenclature.composants:
            # Pas de composants = article de base (ACHAT ou sans nomenclature)
            result.components_checked = 1
            return result

        # Récupérer les allocations de l'OF parent si fourni
        # IMPORTANT : Les OF FERMES avec allocations ne participent pas à l'allocation virtuelle
        allocations_parent = {}
        if num_of_parent and of_parent_est_ferme:
            allocations_parent = {
                alloc.article: alloc.qte_allouee
                for alloc in self.data_loader.get_allocations_of(num_of_parent)
            }

        # Vérifier chaque composant de la nomenclature
        for composant in nomenclature.composants:
            result.components_checked += 1

            # Calculer la quantité nécessaire pour ce composant
            qte_composant = int(composant.qte_lien * qte_besoin)

            if composant.is_achete():
                # LOGIQUE : Si le composant est déjà alloué à l'OF parent, skip
                if of_parent_est_ferme and composant.article_composant in allocations_parent:
                    # Composant déjà alloué à l'OF FERME → Pas de vérification
                    continue
                else:
                    # Pas alloué → Vérifier le stock disponible
                    stock_result = self._check_stock(composant.article_composant, qte_composant, date_besoin)
                    result.merge(stock_result)

            elif composant.is_fabrique():
                # LOGIQUE : Vérifier le stock disponible d'abord
                stock = self.data_loader.get_stock(composant.article_composant)
                stock_dispo = stock.disponible() if stock else 0

                # Si stock suffisant OU OF parent FERME avec allocation → Pas de vérification d'OF
                if of_parent_est_ferme and composant.article_composant in allocations_parent:
                    # Composant fabriqué déjà alloué → Pas de vérification
                    continue
                elif stock_dispo >= qte_composant:
                    # Stock disponible suffisant → Pas besoin de vérifier l'OF
                    continue
                else:
                    # Stock insuffisant → Vérifier l'OF du composant
                    component_result = self._check_of_composant_fabrique(
                        article=composant.article_composant,
                        qte_besoin=qte_composant,
                        date_besoin=date_besoin,
                        depth=depth + 1,
                    )
                    result.merge(component_result)

        return result

    def _check_of_composant_fabrique(
        self,
        article: str,
        qte_besoin: int,
        date_besoin,
        depth: int,
    ) -> FeasibilityResult:
        """Vérifie un composant fabriqué en cherchant son OF.

        Parameters
        ----------
        article : str
            Article fabriqué à vérifier
        qte_besoin : int
            Quantité nécessaire
        date_besoin : date
            Date de besoin
        depth : int
            Profondeur de récursion

        Returns
        -------
        FeasibilityResult
            Résultat de la vérification
        """
        # 1. Chercher un OF FERME avec date la plus proche
        ofs_ferme = self.data_loader.get_ofs_by_article(
            article=article,
            statut=1,  # FERME
            date_besoin=date_besoin,
        )

        if ofs_ferme:
            # OF FERME trouvé → Ses ACHAT sont OK, mais continuer la récursion
            of_ferme = ofs_ferme[0]  # Le plus proche
            return self._check_article_recursive(
                article=article,
                qte_besoin=qte_besoin,
                date_besoin=date_besoin,
                depth=depth,
                of_parent_est_ferme=True,
                num_of_parent=of_ferme.num_of,  # ← Passer le num_of
            )

        # 2. Pas d'OF FERME → Chercher OF SUGGÉRÉ
        ofs_suggere = self.data_loader.get_ofs_by_article(
            article=article,
            statut=3,  # SUGGÉRÉ
            date_besoin=date_besoin,
        )

        if ofs_suggere:
            # OF SUGGÉRÉ → Vérifier sa faisabilité complète
            of_suggere = ofs_suggere[0]  # Le plus proche
            return self._check_article_recursive(
                article=article,
                qte_besoin=qte_besoin,
                date_besoin=date_besoin,
                depth=depth,
                of_parent_est_ferme=False,
                num_of_parent=of_suggere.num_of,  # ← Passer le num_of
            )

        # 3. Aucun OF trouvé → Fallback sur vérification stock
        # (comportement actuel : vérifier comme si OF SUGGÉRÉ)
        return self._check_article_recursive(
            article=article,
            qte_besoin=qte_besoin,
            date_besoin=date_besoin,
            depth=depth,
            of_parent_est_ferme=False,
            num_of_parent=None,  # Pas d'OF parent
        )

    def _check_stock(self, article: str, qte_besoin: int, date_besoin) -> FeasibilityResult:
        """Vérifie si le stock est suffisant pour un article.

        Utilise le stock virtuel si stock_state est fourni, sinon le stock réel.

        Parameters
        ----------
        article : str
            Code de l'article
        qte_besoin : int
            Quantité nécessaire
        date_besoin : date
            Date de besoin

        Returns
        -------
        FeasibilityResult
            Résultat de la vérification de stock
        """
        result = FeasibilityResult()

        # Récupérer le stock (virtuel ou réel)
        if self.stock_state:
            # Utiliser le stock virtuel (allocation activée)
            stock_dispo = self.stock_state.get_available(article)
        else:
            # Utiliser le stock réel (comportement actuel)
            stock = self.data_loader.get_stock(article)
            if stock is None:
                # Article sans stock = considéré comme en rupture
                result.feasible = False
                result.add_missing(article, qte_besoin)
                result.add_alert(f"Stock non disponible pour l'article {article}")
                return result

            stock_dispo = stock.disponible()

            # Ajouter les réceptions si activé
            if self.use_receptions:
                receptions = self.data_loader.get_receptions(article)
                for reception in receptions:
                    if self.check_date and reception.est_disponible_avant(self.check_date):
                        stock_dispo += reception.quantite_restante
                    elif not self.check_date and reception.est_disponible_avant(date_besoin):
                        stock_dispo += reception.quantite_restante

        # Vérifier si le stock est suffisant
        if stock_dispo < qte_besoin:
            result.feasible = False
            result.add_missing(article, qte_besoin - stock_dispo)

        return result
