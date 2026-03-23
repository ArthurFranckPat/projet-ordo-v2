#!/usr/bin/env python
"""Script pour ajouter la colonne 'Nature consommation' aux nomenclatures."""

import csv
from pathlib import Path

# Composants à marquer comme FORFAIT (1 unité par OF)
# Ce sont des composants de présentation/manutention qui ne rentrent pas dans la fabrication
COMPOSANTS_FORFAIT = {
    # Intercalaires carton
    "E7211": "INTERCALAIRE CARTON 1170x770x3",

    # Ajoutez ici d'autres composants au forfait
    # Exemple: "E1234": "ETIQUETTE",
}

def main():
    """Ajoute la colonne Nature consommation au fichier nomenclatures."""
    input_file = Path("data/statique/nomenclatures.csv")
    output_file = Path("data/statique/nomenclatures_with_nature.csv")

    # Lire le fichier original
    print(f"Lecture de {input_file}...")
    rows = []
    with open(input_file, 'r', encoding='latin1') as f:
        reader = csv.DictReader(f, delimiter=';')
        fieldnames = reader.fieldnames

        for row in reader:
            # Déterminer la nature de consommation
            article = row.get("Article composant", "")

            if article in COMPOSANTS_FORFAIT:
                row["Nature consommation"] = "FORFAIT"
            else:
                row["Nature consommation"] = "PROPORTIONNEL"

            rows.append(row)

    # Écrire le nouveau fichier
    print(f"Écriture de {output_file}...")
    with open(output_file, 'w', encoding='latin1', newline='') as f:
        # Ajouter la nouvelle colonne
        fieldnames_with_nature = fieldnames + ["Nature consommation"]
        writer = csv.DictWriter(f, fieldnames=fieldnames_with_nature, delimiter=';')
        writer.writeheader()
        writer.writerows(rows)

    print(f"✅ Fichier créé : {output_file}")

    # Statistiques
    forfait_count = sum(1 for r in rows if r["Nature consommation"] == "FORFAIT")
    proportionnel_count = sum(1 for r in rows if r["Nature consommation"] == "PROPORTIONNEL")

    print()
    print(f"📊 Statistiques :")
    print(f"   FORFAIT : {forfait_count} lignes")
    print(f"   PROPORTIONNEL : {proportionnel_count} lignes")
    print()

    # Afficher les composants marqués FORFAIT
    print("📋 Composants marqués FORFAIT :")
    for article in COMPOSANTS_FORFAIT:
        designation = COMPOSANTS_FORFAIT[article]
        count = sum(1 for r in rows if r["Article composant"] == article)
        print(f"   {article:15} - {designation:40} ({count} utilisations)")

    print()
    print("⚠️  Pensez à marquer les autres composants au forfait dans COMPOSANTS_FORFAIT")
    print("⚠️  puis relancez ce script.")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
