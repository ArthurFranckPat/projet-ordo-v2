"""Charge calculator for workshop load analysis."""

import re
from datetime import date, timedelta
from typing import Dict, List, Set, Optional

_POSTE_CHARGE_REGEX = re.compile(r"^PP_\d+$")


def _is_valid_poste(poste: str) -> bool:
    """Vérifie si un poste suit le pattern PP_xxx (ex: PP_830, PP_128)."""
    return bool(_POSTE_CHARGE_REGEX.match(poste))


class ChargeCalculator:
    """Calculate workshop charge by poste for multiple horizons."""

    def __init__(self, loader):
        """
        Initialize the calculator.

        Parameters
        ----------
        loader : DataLoader
            Data loader with access to commandes and gammes
        """
        self.loader = loader
        self._calculated_articles: Set[tuple[str, str]] = set()  # (article, poste) pour éviter les cycles

    def _calculate_article_charge_recursive(
        self,
        article: str,
        quantity: float,
        target_poste: str,
        visited: Optional[Set[str]] = None
    ) -> float:
        """
        Calcule récursivement la charge totale d'un article pour un poste.

        Inclut la charge directe de l'article + la charge des composants fabriqués.

        Parameters
        ----------
        article : str
            Code de l'article
        quantity : float
            Quantité à fabriquer
        target_poste : str
            Poste de charge cible (pour éviter de compter d'autres postes)
        visited : Set[str], optional
            Articles déjà visités (pour détecter les cycles)

        Returns
        -------
        float
            Charge totale en heures
        """
        if visited is None:
            visited = set()

        # Détection de cycle
        article_key = f"{article}_{target_poste}"
        if article_key in self._calculated_articles:
            return 0.0  # Déjà calculé dans ce contexte

        if article in visited:
            return 0.0  # Cycle détecté

        visited.add(article)
        self._calculated_articles.add(article_key)

        total_hours = 0.0

        # 1. Charge directe de l'article sur le poste cible
        gamme = self.loader.get_gamme(article)
        if gamme:
            for operation in gamme.operations:
                if (
                    _is_valid_poste(operation.poste_charge)
                    and operation.poste_charge == target_poste
                    and operation.cadence
                    and operation.cadence > 0
                ):
                    total_hours += quantity / operation.cadence

        # 2. Charge des composants fabriqués
        nomenclature = self.loader.get_nomenclature(article)
        if nomenclature:
            for composant in nomenclature.composants:
                if composant.is_fabrique():
                    # Calcul récursif de la charge du composant
                    composant_qty = quantity * composant.qte_lien
                    total_hours += self._calculate_article_charge_recursive(
                        composant.article_composant,
                        composant_qty,
                        target_poste,
                        visited.copy()  # Copie pour éviter les interférences
                    )

        return total_hours

    def calculate_of_charge_recursive(
        self,
        of,
        target_poste: str
    ) -> float:
        """
        Calcule récursivement la charge totale d'un OF pour un poste.

        Parameters
        ----------
        of : OF
            Ordre de fabrication
        target_poste : str
            Poste de charge cible

        Returns
        -------
        float
            Charge totale en heures
        """
        self._calculated_articles.clear()  # Reset pour chaque OF
        return self._calculate_article_charge_recursive(
            of.article,
            of.qte_restante,
            target_poste
        )

    def calculate_charge_for_horizon(
        self,
        reference_date: date,
        horizon_weeks: int,
        matcher=None
    ) -> Dict[str, float]:
        """
        Calcule la charge par poste pour un horizon donné.

        Inclut commandes fermes ET prévisions nettes (après consommation).
        La consommation évite le double-comptage : prévision_nette = max(0, prev - cmd).

        Parameters
        ----------
        reference_date : date
            Date de référence (aujourd'hui)
        horizon_weeks : int
            Nombre de semaines (1=S+1, 2=S+2, etc.)
        matcher : optional
            Non utilisé (conservé pour compatibilité)

        Returns
        -------
        Dict[str, float]
            Dictionnaire poste → heures
        """
        from ...algorithms.forecast_consumption import consume_forecasts_by_article

        start_day = (horizon_weeks - 1) * 7 + 1
        end_day = horizon_weeks * 7
        start_date = reference_date + timedelta(days=start_day)
        end_date = reference_date + timedelta(days=end_day)

        # Tous les besoins dans la fenêtre (commandes + prévisions)
        besoins_in_horizon = [
            c for c in self.loader.commandes_clients
            if c.qte_restante > 0
            and start_date <= c.date_expedition_demandee <= end_date
        ]

        if not besoins_in_horizon:
            return {}

        # Appliquer la consommation : prévision_nette = max(0, prev - commandes)
        besoins_ajustes, _ = consume_forecasts_by_article(besoins_in_horizon)

        if not besoins_ajustes:
            return {}

        # Identifier tous les postes valides couverts par ces besoins
        postes_to_calculate: Set[str] = set()
        for besoin in besoins_ajustes:
            gamme = self.loader.get_gamme(besoin.article)
            if gamme:
                for op in gamme.operations:
                    if _is_valid_poste(op.poste_charge) and op.cadence and op.cadence > 0:
                        postes_to_calculate.add(op.poste_charge)

        # Calculer la charge récursive par poste pour chaque besoin
        hours_per_poste: Dict[str, float] = {}
        for poste in postes_to_calculate:
            for besoin in besoins_ajustes:
                self._calculated_articles.clear()
                charge = self._calculate_article_charge_recursive(
                    besoin.article, besoin.qte_restante, poste
                )
                if charge > 0:
                    hours_per_poste[poste] = hours_per_poste.get(poste, 0) + charge

        return hours_per_poste

    def calculate_charge_horizons(
        self,
        reference_date: date,
        matcher
    ) -> Dict[str, 'PosteChargeResult']:
        """
        Calcule la charge pour tous les horizons S+1 à S+4.

        Returns
        -------
        Dict[str, PosteChargeResult]
            Dictionnaire poste → résultat avec charges S+1 à S+4
        """
        from .models import PosteChargeResult

        all_postes = set()

        # Calculer pour chaque horizon
        charges_by_horizon = {}
        for week in range(1, 5):
            charges = self.calculate_charge_for_horizon(
                reference_date=reference_date,
                horizon_weeks=week,
                matcher=matcher
            )
            charges_by_horizon[week] = charges
            all_postes.update(charges.keys())

        # Construire les résultats par poste
        results = {}
        for poste in sorted(all_postes):
            results[poste] = PosteChargeResult(
                poste=poste,
                charge_s1=charges_by_horizon[1].get(poste, 0.0),
                charge_s2=charges_by_horizon[2].get(poste, 0.0),
                charge_s3=charges_by_horizon[3].get(poste, 0.0),
                charge_s4=charges_by_horizon[4].get(poste, 0.0)
            )

        return results
