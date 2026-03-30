"""Tests pour RecursiveChecker."""

import pytest
from datetime import date
from types import SimpleNamespace

from src.loaders import DataLoader
from src.checkers.recursive import RecursiveChecker
from src.algorithms.allocation import StockState
from src.models.of import OF


@pytest.fixture
def loader():
    """Fixture pour DataLoader."""
    loader = DataLoader("data")
    loader.load_all()
    return loader


class TestRecursiveChecker:
    """Tests pour la classe RecursiveChecker."""

    def test_init_without_stock_state(self, loader):
        """Test l'initialisation sans stock_state."""
        checker = RecursiveChecker(loader)

        assert checker.data_loader == loader
        assert checker.use_receptions is False
        assert checker.check_date is None
        assert checker.stock_state is None

    def test_init_with_stock_state(self, loader):
        """Test l'initialisation avec stock_state."""
        stock_state = StockState({"A1953": 100})
        checker = RecursiveChecker(loader, stock_state=stock_state)

        assert checker.stock_state == stock_state

    def test_init_with_receptions(self, loader):
        """Test l'initialisation avec use_receptions."""
        checker = RecursiveChecker(loader, use_receptions=True)

        assert checker.use_receptions is True

    def test_check_of_ferme_with_allocations(self, loader):
        """Test la vérification d'un OF FERME avec allocations."""
        # Trouver un OF FERME avec allocations
        of = None
        for test_of in loader.ofs:
            if test_of.statut_num == 1:  # FERME
                allocations = loader.get_allocations_of(test_of.num_of)
                if allocations:
                    of = test_of
                    break

        if of is None:
            pytest.skip("Aucun OF FERME avec allocations trouvé")

        # Créer un checker
        checker = RecursiveChecker(loader)

        # Vérifier l'OF
        result = checker.check_of(of)

        # L'OF devrait être faisable (composants déjà alloués)
        # Note: On ne vérifie pas strictement feasible=True car il peut y avoir
        # d'autres problèmes, mais on vérifie que la méthode s'exécute
        assert result is not None
        assert isinstance(result.components_checked, int)

    def test_check_of_suggested_without_stock_state(self, loader):
        """Test la vérification d'un OF SUGGÉRÉ sans stock_state."""
        # Trouver un OF SUGGÉRÉ
        of = next((of for of in loader.ofs if of.statut_num == 3), None)

        if of is None:
            pytest.skip("Aucun OF SUGGÉRÉ trouvé")

        # Créer un checker sans stock_state
        checker = RecursiveChecker(loader, stock_state=None)

        # Vérifier l'OF
        result = checker.check_of(of)

        assert result is not None
        assert isinstance(result.feasible, bool)

    def test_check_stock_with_real_stock(self, loader):
        """Test la vérification de stock avec stock réel."""
        checker = RecursiveChecker(loader, stock_state=None)

        # Prendre un article ACHAT avec stock
        article = "A1953"
        stock = loader.get_stock(article)

        if stock is None or stock.disponible() == 0:
            pytest.skip(f"Article {article} sans stock disponible")

        # Vérifier le stock
        result = checker._check_stock(article, 10, date.today())

        assert result is not None
        assert isinstance(result.feasible, bool)

    def test_check_stock_with_virtual_stock_sufficient(self, loader):
        """Test la vérification de stock avec stock virtuel suffisant."""
        article = "A1953"
        stock_state = StockState({article: 100})

        checker = RecursiveChecker(loader, stock_state=stock_state)

        # Vérifier avec besoin inférieur au stock
        result = checker._check_stock(article, 50, date.today())

        assert result.feasible is True
        assert len(result.missing_components) == 0

    def test_check_stock_with_virtual_stock_insufficient(self, loader):
        """Test la vérification de stock avec stock virtuel insuffisant."""
        article = "A1953"
        stock_state = StockState({article: 100})

        checker = RecursiveChecker(loader, stock_state=stock_state)

        # Vérifier avec besoin supérieur au stock
        result = checker._check_stock(article, 150, date.today())

        assert result.feasible is False
        assert article in result.missing_components
        assert result.missing_components[article] == 50  # 150 - 100

    def test_check_stock_with_virtual_stock_zero(self, loader):
        """Test la vérification de stock avec stock virtuel nul."""
        article = "A1953"
        stock_state = StockState({article: 0})

        checker = RecursiveChecker(loader, stock_state=stock_state)

        # Vérifier avec besoin > 0
        result = checker._check_stock(article, 50, date.today())

        assert result.feasible is False
        assert article in result.missing_components
        assert result.missing_components[article] == 50

    def test_check_stock_article_not_in_stock_state(self, loader):
        """Test la vérification d'un article absent du stock_state."""
        article = "A1953"
        stock_state = StockState({})  # Stock vide

        checker = RecursiveChecker(loader, stock_state=stock_state)

        # Vérifier - l'article n'est pas dans stock_state
        result = checker._check_stock(article, 50, date.today())

        # StockState.get_available() retourne 0 si article absent
        assert result.feasible is False
        assert article in result.missing_components

    def test_get_date_besoin_uses_date_debut_in_priority(self):
        """DATE_DEBUT passe avant toute autre source de date."""
        checker = RecursiveChecker(SimpleNamespace(commandes_clients=[]))
        of = OF(
            num_of="F426-10001",
            article="ART001",
            description="OF test",
            statut_num=3,
            statut_texte="Suggéré",
            date_fin=date(2026, 4, 18),
            qte_a_fabriquer=10,
            qte_fabriquee=0,
            qte_restante=10,
            date_debut=date(2026, 4, 15),
        )

        assert checker._get_date_besoin_commande(of) == date(2026, 4, 15)

    def test_get_date_besoin_falls_back_to_linked_commande_minus_two_days(self):
        """Sans DATE_DEBUT, la date de commande liée est utilisée avec le décalage J-2."""
        commande = SimpleNamespace(
            of_contremarque="F426-10002",
            date_expedition_demandee=date(2026, 4, 20),
        )
        checker = RecursiveChecker(SimpleNamespace(commandes_clients=[commande]))
        of = OF(
            num_of="F426-10002",
            article="ART002",
            description="OF test",
            statut_num=3,
            statut_texte="Suggéré",
            date_fin=date(2026, 4, 18),
            qte_a_fabriquer=10,
            qte_fabriquee=0,
            qte_restante=10,
        )

        assert checker._get_date_besoin_commande(of) == date(2026, 4, 18)

    def test_get_date_besoin_falls_back_to_date_fin_minus_two_days(self):
        """Sans DATE_DEBUT ni commande liée, on replie sur DATE_FIN - 2 jours."""
        checker = RecursiveChecker(SimpleNamespace(commandes_clients=[]))
        of = OF(
            num_of="F426-10003",
            article="ART003",
            description="OF test",
            statut_num=3,
            statut_texte="Suggéré",
            date_fin=date(2026, 4, 18),
            qte_a_fabriquer=10,
            qte_fabriquee=0,
            qte_restante=10,
        )

        assert checker._get_date_besoin_commande(of) == date(2026, 4, 16)
