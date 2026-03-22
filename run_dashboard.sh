#!/bin/bash

# Script de lancement du dashboard S+1

echo "🚀 Lancement du dashboard S+1..."

# Vérifier Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 non trouvé"
    exit 1
fi

# Vérifier dépendances
echo "📦 Vérification des dépendances..."
pip install -q streamlit plotly altair

# Lancer Streamlit
echo "🌐 Ouverture du dashboard..."
streamlit run src/dashboards/app.py --server.port 8501 --server.headless false
