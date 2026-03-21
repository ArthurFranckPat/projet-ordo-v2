"""DataLoader - Interface de requête pour les données chargées."""

from collections import defaultdict
from typing import Optional

import pandas as pd

from .csv_loader import CSVLoader
from ..models.article import Article
from ..models.commande_client import CommandeClient
from ..models.nomenclature import Nomenclature
from ..models.of import OF
from ..models.reception import Reception
from ..models.stock import Stock


class DataLoader:
    """DataLoader principal - Interface de requête pour les données.

    Attributes
    ----------
    csv_loader : CSVLoader
        Loader pour les fichiers CSV
    articles : dict[str, Article]
        Catalogue des articles indexé par code
    nomenclatures : dict[str, Nomenclature]
        Nomenclatures indexées par article parent
    ofs : list[OF]
        Liste des ordres de fabrication
    stocks : dict[str, Stock]
        Stocks indexés par article
    receptions : list[Reception]
        Liste des réceptions fournisseurs
    commandes_clients : list[CommandeClient]
        Liste des commandes clients
    """

    def __init__(self, data_dir: str):
        """Initialise le DataLoader.

        Parameters
        ----------
        data_dir : str
            Chemin vers le répertoire contenant les fichiers CSV
        """
        self.csv_loader = CSVLoader(data_dir)

        # Cache pour les données chargées
        self._articles: Optional[dict[str, Article]] = None
        self._nomenclatures: Optional[dict[str, Nomenclature]] = None
        self._ofs: Optional[list[OF]] = None
        self._stocks: Optional[dict[str, Stock]] = None
        self._receptions: Optional[list[Reception]] = None
        self._commandes_clients: Optional[list[CommandeClient]] = None

        # Index des réceptions par article
        self._receptions_by_article: Optional[dict[str, list[Reception]]] = None

        # Index des OF par numéro
        self._ofs_by_num: Optional[dict[str, OF]] = None

    def load_all(self):
        """Charge tous les fichiers CSV en mémoire."""
        (
            self._articles,
            self._nomenclatures,
            self._ofs,
            self._stocks,
            self._receptions,
            self._commandes_clients,
        ) = self.csv_loader.load_all()

        # Indexer les réceptions par article
        self._receptions_by_article = defaultdict(list)
        for reception in self._receptions:
            self._receptions_by_article[reception.article].append(reception)

        # Indexer les OF par numéro
        self._ofs_by_num = {of.num_of: of for of in self._ofs}

    # Méthodes de chargement individuel

    @property
    def articles(self) -> dict[str, Article]:
        """Retourne le catalogue des articles."""
        if self._articles is None:
            self.load_all()
        return self._articles

    @property
    def nomenclatures(self) -> dict[str, Nomenclature]:
        """Retourne les nomenclatures."""
        if self._nomenclatures is None:
            self.load_all()
        return self._nomenclatures

    @property
    def ofs(self) -> list[OF]:
        """Retourne la liste des OF."""
        if self._ofs is None:
            self.load_all()
        return self._ofs

    @property
    def stocks(self) -> dict[str, Stock]:
        """Retourne les stocks."""
        if self._stocks is None:
            self.load_all()
        return self._stocks

    @property
    def receptions(self) -> list[Reception]:
        """Retourne les réceptions."""
        if self._receptions is None:
            self.load_all()
        return self._receptions

    @property
    def commandes_clients(self) -> list[CommandeClient]:
        """Retourne les commandes clients."""
        if self._commandes_clients is None:
            self.load_all()
        return self._commandes_clients

    # Méthodes de requête

    def get_article(self, code: str) -> Optional[Article]:
        """Retourne un article par son code.

        Parameters
        ----------
        code : str
            Code de l'article

        Returns
        -------
        Optional[Article]
            Article ou None si introuvable
        """
        return self.articles.get(code)

    def get_nomenclature(self, article: str) -> Optional[Nomenclature]:
        """Retourne la nomenclature d'un article.

        Parameters
        ----------
        article : str
            Code de l'article parent

        Returns
        -------
        Optional[Nomenclature]
            Nomenclature ou None si introuvable
        """
        return self.nomenclatures.get(article)

    def get_stock(self, article: str) -> Optional[Stock]:
        """Retourne le stock d'un article.

        Parameters
        ----------
        article : str
            Code de l'article

        Returns
        -------
        Optional[Stock]
            Stock ou None si introuvable
        """
        return self.stocks.get(article)

    def get_receptions(self, article: str) -> list[Reception]:
        """Retourne les réceptions pour un article.

        Parameters
        ----------
        article : str
            Code de l'article

        Returns
        -------
        list[Reception]
            Liste des réceptions pour l'article (vide si aucune)
        """
        if self._receptions_by_article is None:
            self.load_all()
        return self._receptions_by_article.get(article, [])

    def get_ofs_to_check(self) -> list[OF]:
        """Retourne la liste des OF à vérifier (OF avec quantité restante > 0).

        Returns
        -------
        list[OF]
            Liste des OF à vérifier
        """
        return [of for of in self.ofs if of.qte_restante > 0]

    def get_articles_fabrication(self) -> list[Article]:
        """Retourne la liste des articles de type FABRICATION.

        Returns
        -------
        list[Article]
            Liste des articles fabriqués
        """
        return [a for a in self.articles.values() if a.is_fabrication()]

    def get_articles_achat(self) -> list[Article]:
        """Retourne la liste des articles de type ACHAT.

        Returns
        -------
        list[Article]
            Liste des articles achetés
        """
        return [a for a in self.articles.values() if a.is_achat()]

    def get_of_by_num(self, num_of: str) -> Optional[OF]:
        """Retourne un OF par son numéro.

        Parameters
        ----------
        num_of : str
            Numéro de l'OF

        Returns
        -------
        Optional[OF]
            OF ou None si introuvable
        """
        if self._ofs_by_num is None:
            self.load_all()
        return self._ofs_by_num.get(num_of)

    def get_commandes_s1(self, date_reference, horizon_days: int = 7) -> list[CommandeClient]:
        """Retourne les commandes clients à expédier dans l'horizon donné.

        Parameters
        ----------
        date_reference : date
            Date de référence
        horizon_days : int
            Horizon en jours (défaut: 7 pour S+1)

        Returns
        -------
        list[CommandeClient]
            Commandes avec DATE_EXPEDITION_DEMANDEE dans l'horizon
        """
        from datetime import timedelta

        date_fin = date_reference + timedelta(days=horizon_days)

        commandes_s1 = []
        for commande in self.commandes_clients:
            date_exp = commande.date_expedition_demandee
            if date_reference <= date_exp <= date_fin and commande.qte_restante > 0:
                commandes_s1.append(commande)

        return commandes_s1
