"""Modèle OF (Ordre de Fabrication)."""

from dataclasses import dataclass
from datetime import date
from enum import Enum


class StatutOF(Enum):
    """Statut d'un OF."""

    FERME = 1
    SUGGERE = 3
    # Ajouter d'autres statuts si nécessaire


@dataclass
class OF:
    """Ordre de fabrication.

    Attributes
    ----------
    num_of : str
        Numéro d'OF (identifiant unique)
    article : str
        Code article à fabriquer
    description : str
        Description de l'article
    statut_num : int
        Code du statut (1 = Ferme, 3 = Suggéré, etc.)
    statut_texte : str
        Statut en texte ("Ferme", "Suggéré", etc.)
    date_fin : date
        Date de fin prévue
    qte_a_fabriquer : int
        Quantité à fabriquer
    qte_fabriquee : int
        Quantité déjà fabriquée
    qte_restante : int
        Quantité restante à fabriquer
    """

    num_of: str
    article: str
    description: str
    statut_num: int
    statut_texte: str
    date_fin: date
    qte_a_fabriquer: int
    qte_fabriquee: int
    qte_restante: int

    def is_ferme(self) -> bool:
        """Vérifie si l'OF est ferme (WOP)."""
        return self.statut_num == 1

    def is_suggere(self) -> bool:
        """Vérifie si l'OF est suggéré (WOS)."""
        return self.statut_num == 3

    @classmethod
    def from_csv_row(cls, row: dict) -> "OF":
        """Crée un OF à partir d'une ligne CSV.

        Parameters
        ----------
        row : dict
            Dictionnaire contenant les champs du CSV

        Returns
        -------
        OF
            Instance d'OF créée à partir de la ligne CSV
        """
        from datetime import datetime

        date_str = row.get("DATE_FIN", "")
        if date_str:
            # Essayer le format français (DD/MM/YYYY) d'abord
            try:
                date_fin = datetime.strptime(date_str, "%d/%m/%Y").date()
            except ValueError:
                # Essayer le format ISO (YYYY-MM-DD)
                try:
                    date_fin = datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    date_fin = date.today()
        else:
            date_fin = date.today()

        def _parse_int(value) -> int:
            """Convertit une valeur en int, en gérant les virgules de milliers."""
            if isinstance(value, (int, float)):
                return int(value)
            if isinstance(value, str):
                cleaned = value.replace(",", "").replace(" ", "").strip()
                if cleaned == "" or cleaned == "-" or cleaned == "NaN":
                    return 0
                return int(float(cleaned))
            return 0

        return cls(
            num_of=row.get("NUM_OF", ""),
            article=row.get("ARTICLE", ""),
            description=row.get("DESCRIPTION", ""),
            statut_num=_parse_int(row.get("STATUT_NUM_OF", 3)),
            statut_texte=row.get("STATUT_TEXTE_OF", "Suggéré"),
            date_fin=date_fin,
            qte_a_fabriquer=_parse_int(row.get("QTE_A_FABRIQUER", 0)),
            qte_fabriquee=_parse_int(row.get("QTE_FABRIQUEE", 0)),
            qte_restante=_parse_int(row.get("QTE_RESTANTE", 0)),
        )

    def __repr__(self) -> str:
        """Représentation textuelle de l'OF."""
        return (
            f"OF({self.num_of}: {self.article} - {self.qte_restante} "
            f"à fabriquer avant le {self.date_fin})"
        )
