#!/usr/bin/env python
"""Test rapide pour vérifier la prise en compte de la nature consommation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.loaders.csv_loader import CSVLoader

# Charger les nomenclatures (le fichier nomenclatures.csv contient maintenant la nature consommation)
loader = CSVLoader(data_dir="data")

nomenclatures = loader.load_nomenclatures()

# Chercher E7211
print("Recherche de E7211 dans les nomenclatures...")
compteur = 0
for article_parent, nomenclature in nomenclatures.items():
    for comp in nomenclature.composants:
        if comp.article_composant == "E7211":
            compteur += 1
            if compteur <= 3:
                print(f"  {article_parent} - Niveau {comp.niveau}")
                print(f"    Qté lien: {comp.qte_lien}")
                print(f"    Nature: {comp.nature_consommation}")
                print()

print(f"Total: {compteur} utilisations de E7211 trouvées")
print(f"Dont marquées FORFAIT: {sum(1 for n in nomenclatures.values() for c in n.composants if c.article_composant == 'E7211' and c.nature_consommation.value == 'FORFAIT')}")
