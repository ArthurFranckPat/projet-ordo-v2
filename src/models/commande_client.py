"""Modèle CommandeClient."""

from dataclasses import dataclass
from datetime import date


@dataclass
class CommandeClient:
    """Commande client.

    Attributes
    ----------
    num_commande : str
        Numéro de commande
    ligne_commande : int
        Numéro de ligne de commande
    code_client : str
        Code client
    nom_client : str
        Nom du client
    article : str
        Code article commandé
    description : str
        Description de l'article
    qte_commandee : int
        Quantité commandée
    qte_allouee : int
        Quantité déjà allouée
    qte_restante : int
        Quantité restante à servir
    date_expedition_demandee : date
        Date d'expédition demandée
    flag_contremarque : int
        Type de commande (5 = MTS, 1 = NOR/MTO)
    of_contremarque : str
        Numéro d'OF lié (MTS uniquement)
    """

    num_commande: str
    ligne_commande: int
    code_client: str
    nom_client: str
    article: str
    description: str
    qte_commandee: int
    qte_allouee: int
    qte_restante: int
    date_expedition_demandee: date
    flag_contremarque: int
    of_contremarque: str

    def is_mts(self) -> bool:
        """Vérifie si la commande est MTS (Make To Stock)."""
        return self.flag_contremarque == 5

    def is_nor_mto(self) -> bool:
        """Vérifie si la commande est NOR/MTO (Normal/Make To Order)."""
        return self.flag_contremarque == 1

    @classmethod
    def from_csv_row(cls, row: dict) -> "CommandeClient":
        """Crée une CommandeClient à partir d'une ligne CSV.

        Parameters
        ----------
        row : dict
            Dictionnaire contenant les champs du CSV

        Returns
        -------
        CommandeClient
            Instance de CommandeClient créée à partir de la ligne CSV
        """
        from datetime import datetime

        # Parser la date d'expédition (format français JJ/MM/AAAA)
        date_str = row.get("DATE_EXPEDITION_DEMANDEE", "")
        if date_str:
            try:
                date_expedition = datetime.strptime(date_str, "%d/%m/%Y").date()
            except ValueError:
                date_expedition = date.today()
        else:
            date_expedition = date.today()

        # Parser les quantités avec gestion des virgules de milliers
        def _parse_int(value) -> int:
            if isinstance(value, (int, float)):
                return int(value)
            if isinstance(value, str):
                cleaned = value.replace(",", "").replace(" ", "").strip()
                if cleaned == "" or cleaned == "-" or cleaned == "NaN":
                    return 0
                return int(float(cleaned))
            return 0

        return cls(
            num_commande=row.get("NUM_COMMANDE", ""),
            ligne_commande=_parse_int(row.get("LIGNE_COMMANDE", 0)),
            code_client=row.get("CODE_CLIENT", ""),
            nom_client=row.get("NOM_CLIENT", ""),
            article=row.get("ARTICLE", ""),
            description=row.get("DESCRIPTION", ""),
            qte_commandee=_parse_int(row.get("QTE_COMMANDEE", 0)),
            qte_allouee=_parse_int(row.get("QTE_ALLOUEE", 0)),
            qte_restante=_parse_int(row.get("QTE_RESTANTE", 0)),
            date_expedition_demandee=date_expedition,
            flag_contremarque=_parse_int(row.get("FLAG_CONTREMARQUE", 1)),
            of_contremarque=row.get("OF_CONTREMARQUE", ""),
        )

    def __repr__(self) -> str:
        """Représentation textuelle de la commande."""
        type_str = "MTS" if self.is_mts() else "NOR/MTO"
        return (
            f"CommandeClient({self.num_commande} - {self.article} - "
            f"{self.qte_restante} unités - {type_str} - {self.date_expedition_demandee})"
        )
