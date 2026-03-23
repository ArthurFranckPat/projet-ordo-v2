"""Charge calculator for workshop load analysis."""

from datetime import date, timedelta
from typing import Dict, List


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

    def calculate_charge_for_horizon(
        self,
        reference_date: date,
        horizon_weeks: int,
        matcher
    ) -> Dict[str, float]:
        """
        Calcule la charge par poste pour un horizon donné.

        Parameters
        ----------
        reference_date : date
            Date de référence (aujourd'hui)
        horizon_weeks : int
            Nombre de semaines (1=S+1, 2=S+2, etc.)
        matcher : CommandeOFMatcher
            Matcher pour lier commandes aux OF

        Returns
        -------
        Dict[str, float]
            Dictionnaire poste → heures
        """
        start_day = (horizon_weeks - 1) * 7 + 1
        end_day = horizon_weeks * 7

        start_date = reference_date + timedelta(days=start_day)
        end_date = reference_date + timedelta(days=end_day)

        # Filtrer les commandes dans l'horizon
        commandes_in_horizon = [
            c for c in self.loader.commandes_clients
            if c.est_commande()
            and c.qte_restante > 0
            and start_date <= c.date_expedition_demandee <= end_date
        ]

        if not commandes_in_horizon:
            return {}

        # Matcher commandes → OF
        matching_results = matcher.match_commandes(commandes_in_horizon)

        # Calculer les heures par poste
        hours_per_poste: Dict[str, float] = {}
        for result in matching_results:
            if result.of is None:
                continue

            of = result.of
            gamme = self.loader.get_gamme(of.article)

            if gamme:
                for operation in gamme.operations:
                    if operation.cadence and operation.cadence > 0:
                        h = of.qte_restante / operation.cadence
                        poste = operation.poste_charge
                        hours_per_poste[poste] = hours_per_poste.get(poste, 0) + h

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
