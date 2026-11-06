"""Filtre les OFs selon la disponibilité des composants."""

from typing import Dict, Set, Any


class FeasibilityFilter:
    """Identifie les composants en rupture et filtre les OFs candidats."""

    def extract_stockout_components(self, feasibility_results: Dict[str, Any]) -> Set[str]:
        """Extrait les composants en rupture depuis les résultats de faisabilité S+1."""
        stockouts = set()
        for result in feasibility_results.values():
            if not result.feasible and hasattr(result, 'missing_components'):
                stockouts.update(result.missing_components.keys())
        return stockouts

    def of_uses_stockout_component(self, of, stockout_components: Set[str], loader) -> bool:
        """Retourne True si l'OF utilise au moins un composant ACHAT en rupture (récursif).

        Règle affermissement : seuls les composants ACHAT en rupture bloquent un OF.
        Les composants FABRICATION déclenchent une vérification récursive de leurs propres
        composants ACHAT.
        """
        if not stockout_components:
            return False
        return self._article_uses_stockout_recursive(of.article, stockout_components, loader, set())

    def _article_uses_stockout_recursive(
        self, article: str, stockout_components: Set[str], loader, visited: Set[str]
    ) -> bool:
        """Vérifie récursivement si un article utilise un composant ACHAT en rupture."""
        if article in visited:
            return False  # Cycle détecté
        visited = visited | {article}

        nomenclature = loader.get_nomenclature(article)
        if not nomenclature or not nomenclature.composants:
            return False  # Nomenclature inconnue → pas bloqué par défaut

        for comp in nomenclature.composants:
            if comp.is_achete() and comp.article_composant in stockout_components:
                return True  # Composant ACHAT en rupture → bloque
            if comp.is_fabrique():
                # Vérification récursive pour les sous-ensembles FABRICATION
                if self._article_uses_stockout_recursive(
                    comp.article_composant, stockout_components, loader, visited
                ):
                    return True
        return False

    def filter_feasible_candidates(self, ofs, stockout_components: Set[str], loader) -> list:
        """Retourne les OFs qui NE consomment PAS les composants en rupture."""
        return [
            of for of in ofs
            if not self.of_uses_stockout_component(of, stockout_components, loader)
        ]
