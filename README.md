# Ordonnancement Production v2

Système de vérification de faisabilité des composants pour l'ordonnancement manufacturier.

## 🎯 Objectif

Permettre à l'ordonnanceur de vérifier rapidement si les composants seront disponibles pour réaliser la production planifiée, en prenant en compte :

- La vérification récursive des nomenclatures (jusqu'aux composants ACHAT)
- La gestion de la concurrence entre OF
- Deux modes de vérification : immédiate (stock) et projetée (stock + réceptions fournisseurs)

## 📋 Prérequis

- Python 3.11+
- pandas
- rich

## 🚀 Installation

```bash
pip install -r requirements.txt
```

## 📖 Utilisation

```bash
python -m src.main --data-dir data
```

## 🏗️ Structure du projet

```
src/
├── models/         # Modèles de données
├── loaders/        # Chargement des CSV
├── checkers/       # Algorithmes de vérification
├── algorithms/     # Gestion de la concurrence
└── utils/          # Formatage et affichage
```

## 📚 Documentation

Voir [CLAUDE.md](CLAUDE.md) pour la documentation complète du système.
