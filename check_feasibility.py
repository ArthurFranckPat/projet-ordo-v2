#!/usr/bin/env python3
"""Script de lancement pour le système de vérification de faisabilité."""

import sys
import os

# Ajouter src au PYTHONPATH
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from src.main import main

if __name__ == "__main__":
    main()
