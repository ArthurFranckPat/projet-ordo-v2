"""Recursive Checker - Algorithme de vérification récursive des nomenclatures."""

from typing import Optional

from .base import BaseChecker, FeasibilityResult
from ..models.nomenclature import Nomenclature
from ..models.of import OF


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
    """

    def __init__(self, data_loader, use_receptions: bool = False, check_date: Optional = None):
        """Initialise le checker récursif.

        Parameters
        ----------
        data_loader : DataLoader
            Loader de données
        use_receptions : bool
            Si True, utilise les réceptions fournisseurs
        check_date : Optional[date]
            Date de vérification (None = aujourd'hui)
        """
        super().__init__(data_loader)
        self.use_receptions = use_receptions
        self.check_date = check_date

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
        return self._check_article_recursive(
            article=of.article,
            qte_besoin=of.qte_restante,
            date_besoin=of.date_fin,
            depth=0,
        )

    def _check_article_recursive(
        self,
        article: str,
        qte_besoin: int,
        date_besoin,
        depth: int,
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

        # Vérifier chaque composant de la nomenclature
        for composant in nomenclature.composants:
            result.components_checked += 1

            # Calculer la quantité nécessaire pour ce composant
            qte_composant = int(composant.qte_lien * qte_besoin)

            if composant.is_achete():
                # Composant ACHAT → vérifier le stock
                stock_result = self._check_stock(composant.article_composant, qte_composant, date_besoin)
                result.merge(stock_result)

            elif composant.is_fabrique():
                # Composant FABRIQUÉ → vérification récursive
                sub_result = self._check_article_recursive(
                    article=composant.article_composant,
                    qte_besoin=qte_composant,
                    date_besoin=date_besoin,
                    depth=depth + 1,
                )
                result.merge(sub_result)

        return result

    def _check_stock(self, article: str, qte_besoin: int, date_besoin) -> FeasibilityResult:
        """Vérifie si le stock est suffisant pour un article.

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

        # Récupérer le stock actuel
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
