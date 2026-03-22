"""CSV Loader - Chargement des fichiers CSV."""

import os
from pathlib import Path
from typing import Optional

import pandas as pd

from ..models.article import Article
from ..models.besoin_client import BesoinClient
from ..models.commande_client import CommandeClient
from ..models.gamme import Gamme, GammeOperation
from ..models.nomenclature import Nomenclature
from ..models.of import OF
from ..models.reception import Reception
from ..models.stock import Stock
from collections import defaultdict


class CSVLoader:
    """Loader pour les fichiers CSV de données de production.

    Attributes
    ----------
    data_dir : Path
        Répertoire racine contenant les sous-dossiers statique/ et dynamique/
    statique_dir : Path
        Répertoire des données statiques (articles, gammes, nomenclatures)
    dynamique_dir : Path
        Répertoire des données dynamiques (commandes, OF, stock, réceptions)
    """

    def __init__(self, data_dir: str | Path):
        """Initialise le loader avec un répertoire de données.

        Parameters
        ----------
        data_dir : str | Path
            Chemin vers le répertoire racine contenant statique/ et dynamique/
        """
        self.data_dir = Path(data_dir)
        if not self.data_dir.exists():
            raise FileNotFoundError(f"Répertoire de données introuvable: {self.data_dir}")

        # Sous-dossiers
        self.statique_dir = self.data_dir / "statique"
        self.dynamique_dir = self.data_dir / "dynamique"

        # Vérifier que les sous-dossiers existent
        if not self.statique_dir.exists():
            raise FileNotFoundError(f"Sous-dossier 'statique' introuvable: {self.statique_dir}")
        if not self.dynamique_dir.exists():
            raise FileNotFoundError(f"Sous-dossier 'dynamique' introuvable: {self.dynamique_dir}")

    def _load_csv(self, filename: str, subdir: str = None, sep: str = ";") -> pd.DataFrame:
        """Charge un fichier CSV dans un DataFrame.

        Parameters
        ----------
        filename : str
            Nom du fichier CSV
        subdir : str, optional
            Sous-dossier ("statique" ou "dynamique"). Si None, utilise le répertoire racine.
        sep : str
            Séparateur (défaut: ";" pour les CSV français)

        Returns
        -------
        pd.DataFrame
            DataFrame contenant les données du CSV

        Raises
        ------
        FileNotFoundError
            Si le fichier n'existe pas
        """
        # Déterminer le répertoire approprié
        if subdir:
            target_dir = self.data_dir / subdir
        else:
            target_dir = self.data_dir

        filepath = target_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"Fichier introuvable: {filepath}")

        # Essayer UTF-8 d'abord, puis latin-1 si ça échoue
        try:
            return pd.read_csv(filepath, sep=sep, encoding="utf-8", low_memory=False)
        except UnicodeDecodeError:
            return pd.read_csv(filepath, sep=sep, encoding="latin-1", low_memory=False)

    # pylint: disable=too-many-arguments

    def load_articles(self) -> dict[str, Article]:
        """Charge le catalogue des articles.

        Returns
        -------
        dict[str, Article]
            Dictionnaire des articles indexé par code article
        """
        df = self._load_csv("articles.csv", subdir="statique")

        articles = {}
        for _, row in df.iterrows():
            article = Article.from_csv_row(row.to_dict())
            articles[article.code] = article

        return articles

    def load_nomenclatures(self) -> dict[str, Nomenclature]:
        """Charge les nomenclatures articles.

        Returns
        -------
        dict[str, Nomenclature]
            Dictionnaire des nomenclatures indexé par article parent
        """
        df = self._load_csv("nomenclatures.csv", subdir="statique")

        # Grouper par article parent
        nomenclatures = {}
        for article_parent, group in df.groupby("Article parent"):
            nomenclatures[article_parent] = Nomenclature.from_csv_rows(
                article=article_parent, rows=group.to_dict("records")
            )

        return nomenclatures

    def load_gammes(self) -> dict[str, Gamme]:
        """Charge les gammes de production.

        Returns
        -------
        dict[str, Gamme]
            Dictionnaire des gammes indexé par article
        """
        df = self._load_csv("gammes.csv", subdir="statique")

        # Grouper par article
        gammes_dict = defaultdict(list)
        for _, row in df.iterrows():
            op = GammeOperation.from_csv_row(row.to_dict())
            gammes_dict[op.article].append(op)

        # Convertir en objets Gamme
        gammes = {
            article: Gamme(article=article, operations=ops)
            for article, ops in gammes_dict.items()
        }

        return gammes

    def load_of_entetes(self) -> list[OF]:
        """Charge les en-têtes d'ordres de fabrication.

        Returns
        -------
        list[OF]
            Liste des OF
        """
        df = self._load_csv("of_entetes.csv", subdir="dynamique")

        ofs = []
        for _, row in df.iterrows():
            of = OF.from_csv_row(row.to_dict())
            ofs.append(of)

        return ofs

    def load_stock(self) -> dict[str, Stock]:
        """Charge l'état des stocks.

        Returns
        -------
        dict[str, Stock]
            Dictionnaire des stocks indexé par article
        """
        df = self._load_csv("stock.csv", subdir="dynamique")

        stocks = {}
        for _, row in df.iterrows():
            stock = Stock.from_csv_row(row.to_dict())
            stocks[stock.article] = stock

        return stocks

    def load_receptions(self) -> list[Reception]:
        """Charge les réceptions fournisseurs.

        Returns
        -------
        list[Reception]
            Liste des réceptions
        """
        df = self._load_csv("receptions_oa.csv", subdir="dynamique")

        receptions = []
        for _, row in df.iterrows():
            reception = Reception.from_csv_row(row.to_dict())
            receptions.append(reception)

        return receptions

    def load_commandes_clients(self) -> list[BesoinClient]:
        """Charge les commandes clients.

        Priority: besoins_clients.csv > commandes_clients.csv (legacy)

        Returns
        -------
        list[BesoinClient]
            Liste des besoins clients (toujours au nouveau format)
        """
        try:
            # Essayer besoins_clients.csv d'abord
            df = self._load_csv("besoins_clients.csv", subdir="dynamique")
            return self._load_besoins_from_df(df)
        except FileNotFoundError:
            # Fallback sur commandes_clients.csv (legacy)
            df = self._load_csv("commandes_clients.csv", subdir="dynamique")
            # Convertir vers le nouveau format BesoinClient
            return self._convert_commandes_legacy_to_besoins(df)

    def _load_besoins_from_df(self, df) -> list[BesoinClient]:
        """Charge les besoins depuis le DataFrame besoins_clients.csv.

        Parameters
        ----------
        df : pd.DataFrame
            DataFrame contenant les données du CSV

        Returns
        -------
        list[BesoinClient]
            Liste des besoins clients
        """
        besoins = []

        for _, row in df.iterrows():
            try:
                besoin = BesoinClient.from_csv_row(row.to_dict())
                if besoin.article:  # Ignorer les lignes sans article
                    besoins.append(besoin)
            except Exception as e:
                # Loguer l'erreur mais continuer
                print(f"Warning: Erreur parsing ligne {_}: {e}")
                continue

        return besoins

    def _convert_commandes_legacy_to_besoins(self, df) -> list[BesoinClient]:
        """Convertit les commandes legacy vers BesoinClient.

        Pour compatibilité avec l'ancien format commandes_clients.csv.
        Convertit FLAG_CONTREMARQUE (5/1) vers TYPE_COMMANDE (MTS/NOR).

        Parameters
        ----------
        df : pd.DataFrame
            DataFrame contenant les données du CSV legacy

        Returns
        -------
        list[BesoinClient]
            Liste des besoins clients convertis
        """
        besoins = []

        for _, row in df.iterrows():
            # Mapper FLAG_CONTREMARQUE vers TYPE_COMMANDE
            flag = int(row.get("FLAG_CONTREMARQUE", 1))
            if flag == 5:
                type_cmd = "MTS"
            else:
                # FLAG 1 (NOR/MTO) ou autre → NOR par défaut
                type_cmd = "NOR"

            # Créer un dict au format BesoinClient
            row_besoin = {
                "NOM_CLIENT": row.get("NOM_CLIENT", ""),
                "TYPE_COMMANDE": type_cmd,
                "NUM_COMMANDE": row.get("NUM_COMMANDE", ""),
                "NATURE_BESOIN": "COMMANDE",
                "ARTICLE": row.get("ARTICLE", ""),
                "OF_CONTREMARQUE": row.get("OF_CONTREMARQUE", ""),
                "DATE_COMMANDE": "",  # Pas d'info dans l'ancien format
                "DATE_EXPEDITION_DEMANDEE": row.get("DATE_EXPEDITION_DEMANDEE", ""),
                "QTE_COMMANDEE": row.get("QTE_COMMANDEE", 0),
                "QTE_ALLOUEE": row.get("QTE_ALLOUEE", 0),
                "QTE_RESTANTE": row.get("QTE_RESTANTE", 0),
            }

            try:
                besoin = BesoinClient.from_csv_row(row_besoin)
                if besoin.article:
                    besoins.append(besoin)
            except Exception as e:
                print(f"Warning: Erreur conversion legacy: {e}")
                continue

        return besoins

    def load_all(
        self,
    ) -> tuple[
        dict[str, Article],
        dict[str, Nomenclature],
        dict[str, Gamme],
        list[OF],
        dict[str, Stock],
        list[Reception],
        list[BesoinClient],
    ]:
        """Charge tous les fichiers CSV.

        Returns
        -------
        tuple
            (articles, nomenclatures, gammes, ofs, stocks, receptions, commandes_clients)

        Note
        ----
        commandes_clients est maintenant de type list[BesoinClient] (pas CommandeClient).
        """
        articles = self.load_articles()
        nomenclatures = self.load_nomenclatures()
        gammes = self.load_gammes()
        ofs = self.load_of_entetes()
        stocks = self.load_stock()
        receptions = self.load_receptions()
        commandes_clients = self.load_commandes_clients()

        return articles, nomenclatures, gammes, ofs, stocks, receptions, commandes_clients
