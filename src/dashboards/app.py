"""Application Streamlit principale - Dashboard S+1."""

import streamlit as st
import sys
from pathlib import Path
from datetime import date

# Ajouter le répertoire racine au path Python
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.loaders.data_loader import DataLoader
from src.algorithms.matching import CommandeOFMatcher
from src.checkers.immediate import ImmediateChecker
from src.checkers.projected import ProjectedChecker
from src.checkers.recursive import RecursiveChecker
from src.algorithms.allocation import AllocationManager, AllocationResult, AllocationStatus


# --- CONFIGURATION ---
st.set_page_config(
    page_title="Dashboard S+1 - Ordonnancement",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)


# --- LOAD DATA ---
@st.cache_resource
def load_data(data_dir: str) -> DataLoader:
    """Charge les données depuis CSV."""
    loader = DataLoader(data_dir)
    loader.load_all()
    return loader


# --- SIDEBAR ---
def sidebar():
    """Affiche la sidebar avec configuration."""
    st.sidebar.title("⚙️ Configuration")

    data_dir = st.sidebar.text_input(
        "Répertoire données",
        value="data",
        help="Chemin vers le répertoire contenant les fichiers CSV"
    )

    st.sidebar.markdown("---")

    # Période
    st.sidebar.subheader("📅 Période")
    date_ref = st.sidebar.date_input("Date de référence", value=date.today())
    horizon = st.sidebar.slider("Horizon (jours)", min_value=1, max_value=30, value=7)

    st.sidebar.markdown("---")

    # Options
    st.sidebar.subheader("⚙️ Options")
    include_previsions = st.sidebar.checkbox("Inclure les prévisions", value=False)
    gerer_concurrence = st.sidebar.checkbox("Gérer la concurrence entre OF", value=True)
    inclure_livraisons = st.sidebar.checkbox("Inclure les livraisons fournisseurs", value=True)

    st.sidebar.markdown("---")

    # Affichage des paramètres
    st.sidebar.subheader("📋 Vos paramètres")
    st.sidebar.caption(f"📅 Du : {date_ref.strftime('%d/%m/%Y')}")
    st.sidebar.caption(f"📆 Horizon : {horizon} jours")
    st.sidebar.caption(f"📊 Prévisions : {'Oui' if include_previsions else 'Non'}")
    st.sidebar.caption(f"📦 Concurrence : {'Oui' if gerer_concurrence else 'Non'}")
    st.sidebar.caption(f"🚚 Livraisons : {'Oui' if inclure_livraisons else 'Non'}")

    return data_dir, date_ref, horizon, include_previsions, gerer_concurrence, inclure_livraisons


# --- COMPUTE S1 ---
def compute_s1(
    loader: DataLoader,
    date_ref: date,
    horizon: int,
    include_previsions: bool,
    gerer_concurrence: bool,
    inclure_livraisons: bool
):
    """Calcule les résultats S+1."""
    try:
        # Récupérer les besoins S+1
        besoins_s1 = loader.get_commandes_s1(
            date_reference=date_ref,
            horizon_days=horizon,
            include_previsions=include_previsions
        )

        # Matcher les commandes avec les OF
        matcher = CommandeOFMatcher(loader, date_tolerance_days=10)
        resultats_matching = matcher.match_commandes(besoins_s1)

        # Sélectionner les OF à vérifier
        ofs = [r.of for r in resultats_matching if r.of is not None]

        # Choisir le checker selon les options
        if inclure_livraisons:
            checker = RecursiveChecker(
                loader,
                use_receptions=True,
                check_date=date_ref
            )
        else:
            checker = ImmediateChecker(loader)

        # Gérer ou non la concurrence
        if gerer_concurrence:
            # Allocation virtuelle avec gestion de la concurrence
            allocation_manager = AllocationManager(loader, checker)
            allocation_results = allocation_manager.allocate_stock(ofs)

            # Extraire les résultats de faisabilité
            resultats_faisabilite = {}
            for of_num, alloc_result in allocation_results.items():
                resultats_faisabilite[of_num] = alloc_result.feasibility_result
        else:
            # Pas de gestion de la concurrence
            resultats_faisabilite = checker.check_all_ofs(ofs)

            # Créer des allocation_results vides pour compatibilité
            allocation_results = {}
            for of_num, result in resultats_faisabilite.items():
                allocation_results[of_num] = AllocationResult(
                    of_num=of_num,
                    status=AllocationStatus.FEASIBLE if result.feasible else AllocationStatus.NOT_FEASIBLE,
                    feasibility_result=result,
                    allocated_quantity={}
                )

        return besoins_s1, resultats_matching, resultats_faisabilite, allocation_results

    except Exception as e:
        st.error(f"❌ Erreur lors du calcul S+1: {e}")
        st.exception(e)
        return [], [], {}, {}


# --- PAGE 1: VUE D'ENSEMBLE ---
def show_overview():
    """Page 1 : Vue d'ensemble."""
    st.header("📊 Vue d'ensemble")

    # Récupérer les données du session_state
    if 'resultats_matching' not in st.session_state:
        st.warning("⚠️ Lancez d'abord le calcul S+1 depuis la page d'accueil")
        return

    resultats_matching = st.session_state.resultats_matching
    resultats_faisabilite = st.session_state.resultats_faisabilite
    allocation_results = st.session_state.allocation_results

    # Métriques
    if resultats_matching:
        total = len(resultats_matching)
        of_trouves = sum(1 for r in resultats_matching if r.of is not None)
        taux = (of_trouves / total * 100) if total > 0 else 0

        of_verifies = [r.of for r in resultats_matching if r.of is not None]
        faisables = sum(
            1
            for of in of_verifies
            if of.num_of in resultats_faisabilite
            and resultats_faisabilite[of.num_of].feasible
        )

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Commandes", total)
        col2.metric("Servies", of_trouves)
        col3.metric("Taux service", f"{taux:.1f}%")
        col4.metric("OF faisables", faisables)

    # Tableau matching
    st.subheader("🔗 Résultats du matching")

    if resultats_matching:
        data = []
        of_statuts = []  # Stocker les statuts séparément pour le coloriage
        for r in resultats_matching:
            c = r.commande
            of_num = r.of.num_of if r.of else 'Aucun'
            of_statut = None

            if r.of and r.of.num_of in resultats_faisabilite:
                faisable = resultats_faisabilite[r.of.num_of].feasible
                faisable_str = "✅" if faisable else "❌"
                # Récupérer le statut de l'OF
                of_statut = r.of.statut_num if r.of else None
            else:
                faisable_str = "STOCK"

            data.append({
                'Commande': c.num_commande,
                'Client': c.nom_client,
                'Article': c.article,
                'Qté': c.qte_restante,
                'Date': c.date_expedition_demandee.strftime('%d/%m/%Y'),
                'Type': c.type_commande.value,
                'Nature': 'CMD' if c.est_commande() else 'PRÉV',
                'OF': of_num,
                'Faisable': faisable_str
            })
            of_statuts.append(of_statut)

        import pandas as pd
        df = pd.DataFrame(data)

        # Colorer les lignes selon le statut
        def colorer_lignes(row):
            idx = row.name
            of_statut = of_statuts[idx]

            if row['OF'] == 'Aucun':
                # Vert clair : couvert par stock
                return ['background-color: #d4edda'] * len(row)
            elif row['Faisable'] == '✅' and of_statut == 1:
                # Bleu clair : OF ferme et faisable
                return ['background-color: #cce5ff'] * len(row)
            elif row['Faisable'] == '✅' and of_statut == 3:
                # Jaune clair : OF suggéré et faisable (affermissable)
                return ['background-color: #fff3cd'] * len(row)
            elif row['Faisable'] == '❌':
                # Rouge clair : OF non faisable
                return ['background-color: #f8d7da'] * len(row)
            return [''] * len(row)

        df_styled = df.style.apply(colorer_lignes, axis=1)
        st.dataframe(df_styled, use_container_width=True, height=400)


# --- PAGE 2: COMPOSANTS EN RUPTURE ---
def show_composants_rupture():
    """Page 2 : Composants en rupture."""
    st.header("⚠️ Composants en rupture")

    # Récupérer les données du session_state
    if 'resultats_faisabilite' not in st.session_state:
        st.warning("⚠️ Lancez d'abord le calcul S+1 depuis la page d'accueil")
        return

    loader = st.session_state.loader
    resultats_faisabilite = st.session_state.resultats_faisabilite
    allocation_results = st.session_state.allocation_results
    resultats_matching = st.session_state.resultats_matching

    # Collecter tous les composants manquants avec infos détaillées
    from collections import defaultdict

    composants_manquants = defaultdict(lambda: {
        'quantite_manquante': 0,
        'designation': '',
        'niveau': None,
        'ofs_impactes': [],  # Liste de tuples (of_num, article_of, designation_of)
        'commandes_impactees': []  # Liste de tuples (num_cmd, article, designation, client)
    })

    # Collecter les infos de composants manquants
    for of_num, result in resultats_faisabilite.items():
        if not result.feasible and result.missing_components:
            # Récupérer l'OF pour connaître l'article fabriqué
            of_info = None
            for r in resultats_matching:
                if r.of and r.of.num_of == of_num:
                    of_info = r.of
                    break

            article_of = of_info.article if of_info else "Inconnu"
            designation_of = of_info.description if of_info else "Inconnu"

            for article, qte in result.missing_components.items():
                composants_manquants[article]['quantite_manquante'] += qte
                composants_manquants[article]['ofs_impactes'].append((of_num, article_of, designation_of))

                # Récupérer la désignation et le niveau du composant
                if not composants_manquants[article]['designation']:
                    article_data = loader.get_article(article)
                    if article_data:
                        composants_manquants[article]['designation'] = article_data.description
                        # Le niveau n'est pas directement disponible dans articles.csv,
                        # il faut regarder la nomenclature de l'OF parent
                        composants_manquants[article]['niveau'] = "N/A"

    # Lier les commandes aux composants
    for r in resultats_matching:
        if r.of and r.of.num_of in resultats_faisabilite:
            result = resultats_faisabilite[r.of.num_of]
            if not result.feasible:
                for article in result.missing_components.keys():
                    composants_manquants[article]['commandes_impactees'].append((
                        r.commande.num_commande,
                        r.commande.article,
                        r.commande.description if hasattr(r.commande, 'description') else '',
                        r.commande.nom_client
                    ))

    if not composants_manquants:
        st.success("✅ Aucun composant en rupture !")
        return

    # Afficher les composants en rupture
    st.subheader(f"🚨 {len(composants_manquants)} composant(s) en rupture")

    for article, data in sorted(composants_manquants.items()):
        designation = data['designation']
        titre = f"**{article}** - {designation}" if designation else f"**{article}**"
        with st.expander(f"{titre} - Manquant: {data['quantite_manquante']}", expanded=False):
            col1, col2 = st.columns(2)

            with col1:
                st.markdown(f"**Article :** {article}")
                if designation:
                    st.markdown(f"**Désignation :** {designation}")
                st.markdown(f"**Quantité manquante :** {data['quantite_manquante']} unités")
                st.markdown("---")
                st.markdown("**OF impacté(s) :**")
                for of_num, article_of, designation_of in data['ofs_impactes']:
                    if designation_of:
                        st.markdown(f"- **{of_num}** → {article_of} ({designation_of})")
                    else:
                        st.markdown(f"- **{of_num}** → {article_of}")

            with col2:
                st.markdown("**Commandes impactées :**")
                for num_cmd, article_cmd, designation_cmd, client in data['commandes_impactees']:
                    if designation_cmd:
                        st.markdown(f"- **{num_cmd}** ({client})")
                        st.markdown(f"  ↳ {article_cmd} - {designation_cmd}")
                    else:
                        st.markdown(f"- **{num_cmd}** ({client}) → {article_cmd}")


# --- PAGE D'ACCUEIL ---
def show_home(data_dir: str, date_ref: date, horizon: int, include_previsions: bool,
              gerer_concurrence: bool, inclure_livraisons: bool):
    """Page d'accueil avec calcul."""
    st.title("📊 Dashboard S+1 - Ordonnancement Production")
    st.markdown("---")

    # Instructions
    st.markdown("""
    ### 🎯 Comment utiliser ce dashboard ?

    1. **Configurez vos paramètres** dans la sidebar ⬅️
    2. **Cliquez sur "Lancer l'analyse"** pour calculer les résultats S+1
    3. **Naviguez vers les pages** pour explorer les résultats :
       - 📊 **Vue d'ensemble** : Métriques et tableau des commandes
       - ⚠️ **Composants en rupture** : Liste des composants manquants et impact
    """)

    st.markdown("---")

    # Bouton pour lancer l'analyse
    if st.button("🚀 Lancer l'analyse S+1", type="primary", use_container_width=True):
        with st.spinner("🔄 Calcul en cours..."):
            try:
                loader = load_data(data_dir)
                besoins_s1, resultats_matching, resultats_faisabilite, allocation_results = compute_s1(
                    loader=loader,
                    date_ref=date_ref,
                    horizon=horizon,
                    include_previsions=include_previsions,
                    gerer_concurrence=gerer_concurrence,
                    inclure_livraisons=inclure_livraisons
                )

                # Stocker dans session_state
                st.session_state.loader = loader
                st.session_state.besoins_s1 = besoins_s1
                st.session_state.resultats_matching = resultats_matching
                st.session_state.resultats_faisabilite = resultats_faisabilite
                st.session_state.allocation_results = allocation_results
                st.session_state.analysis_done = True

                st.success(f"✅ Analyse terminée : {len(resultats_matching)} commandes traitées")
                st.rerun()

            except Exception as e:
                st.error(f"❌ Erreur : {e}")
                st.exception(e)


# --- MAIN ---
def main():
    """Fonction principale."""

    # Sidebar (affichée sur toutes les pages)
    data_dir, date_ref, horizon, include_previsions, gerer_concurrence, inclure_livraisons = sidebar()

    # Navigation entre pages
    page = st.radio(
        "Navigation",
        ["🏠 Accueil", "📊 Vue d'ensemble", "⚠️ Composants en rupture"],
        label_visibility="collapsed"
    )

    # Router
    if page == "🏠 Accueil":
        show_home(data_dir, date_ref, horizon, include_previsions, gerer_concurrence, inclure_livraisons)

    elif page == "📊 Vue d'ensemble":
        if not st.session_state.get('analysis_done', False):
            st.info("👆 Lancez d'abord l'analyse depuis la page d'accueil")
        else:
            show_overview()

    elif page == "⚠️ Composants en rupture":
        if not st.session_state.get('analysis_done', False):
            st.info("👆 Lancez d'abord l'analyse depuis la page d'accueil")
        else:
            show_composants_rupture()


if __name__ == "__main__":
    main()
