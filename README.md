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

## 🖥️ GUI Locale

Une V1 d'interface graphique locale est disponible via :
- une API locale FastAPI
- un frontend React/Vite inspire de shadcn/ui

### Démarrer l'API locale

```bash
uvicorn src.api.server:app --reload
```

### Démarrer le frontend

```bash
cd frontend
npm install
npm run dev
```

Le frontend s'attend par défaut à une API sur `http://127.0.0.1:8000`.
Vous pouvez surcharger l'URL avec `VITE_API_BASE_URL`.

### Vérifications GUI

```bash
cd frontend
npm run build
npm run lint
npm run test
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
