#!/usr/bin/env python3
"""Comparaison des résultats avec/sans allocation virtuelle."""

import sys
from datetime import date
from collections import defaultdict

from src.loaders import DataLoader
from src.checkers.recursive import RecursiveChecker
from src.algorithms.allocation import AllocationManager


def get_ofs_from_commandes_s1(loader, horizon_days=7):
    """Récupère les OFs matchés aux commandes S+1."""
    from src.algorithms.matching import CommandeOFMatcher

    date_ref = date.today()
    commandes_s1 = loader.get_commandes_s1(date_ref, horizon_days)

    print(f"   📋 {len(commandes_s1)} commandes S+1 trouvées")

    # Matcher les commandes avec les OFs
    matcher = CommandeOFMatcher(loader, date_tolerance_days=10)
    resultats_matching = matcher.match_commandes(commandes_s1)

    # Extraire les OFs uniques matchés
    ofs = []
    of_nums = set()
    for resultat in resultats_matching:
        if resultat.of is not None and resultat.of.num_of not in of_nums:
            ofs.append(resultat.of)
            of_nums.add(resultat.of.num_of)

    print(f"   🔗 {len(ofs)} OFs matchés à ces commandes")
    return ofs


def run_verification_without_virtual_allocation(loader):
    """Exécute la vérification SANS allocation virtuelle."""
    print("📦 Vérification SANS allocation virtuelle (avec réceptions fournisseurs)...")

    checker = RecursiveChecker(
        loader,
        use_receptions=True,  # Inclut les réceptions fournisseurs fermes
        check_date=date.today(),
        stock_state=None  # Pas de stock virtuel
    )

    # Récupérer les OFs via les commandes S+1
    ofs = get_ofs_from_commandes_s1(loader, horizon_days=7)

    results = {}
    for of in ofs:
        result = checker.check_of(of)
        results[of.num_of] = result

    return results


def run_verification_with_virtual_allocation(loader):
    """Exécute la vérification AVEC allocation virtuelle."""
    print("📦 Vérification AVEC allocation virtuelle (avec réceptions fournisseurs)...")

    checker = RecursiveChecker(
        loader,
        use_receptions=True,  # Inclut les réceptions fournisseurs fermes
        check_date=date.today()
    )

    allocation_manager = AllocationManager(loader, checker)
    ofs = get_ofs_from_commandes_s1(loader, horizon_days=7)

    allocation_results = allocation_manager.allocate_stock(ofs)

    # Extraire les FeasibilityResult
    results = {
        of_num: result.feasibility_result
        for of_num, result in allocation_results.items()
    }

    return results


def aggregate_missing_components(results):
    """Agrège les composants manquants."""
    missing = defaultdict(int)

    for of_num, result in results.items():
        if not result.feasible:
            for article, qte in result.missing_components.items():
                missing[article] += qte

    return dict(sorted(missing.items(), key=lambda x: -x[1]))


def compare_results(results_no_alloc, results_with_alloc):
    """Compare les deux modes de vérification."""

    print("\n" + "="*80)
    print("COMPARAISON DES RÉSULTATS")
    print("="*80 + "\n")

    # Statistiques générales
    total_ofs = len(results_no_alloc)

    infeasible_no_alloc = sum(1 for r in results_no_alloc.values() if not r.feasible)
    infeasible_with_alloc = sum(1 for r in results_with_alloc.values() if not r.feasible)

    feasible_no_alloc = total_ofs - infeasible_no_alloc
    feasible_with_alloc = total_ofs - infeasible_with_alloc

    print(f"📊 STATISTIQUES GÉNÉRALES")
    print(f"   Total OFs vérifiés : {total_ofs}")
    print()
    print(f"   SANS allocation virtuelle :")
    print(f"     ✅ Faisables  : {feasible_no_alloc} ({100*feasible_no_alloc/total_ofs:.1f}%)")
    print(f"     ❌ Non faisables : {infeasible_no_alloc} ({100*infeasible_no_alloc/total_ofs:.1f}%)")
    print()
    print(f"   AVEC allocation virtuelle :")
    print(f"     ✅ Faisables  : {feasible_with_alloc} ({100*feasible_with_alloc/total_ofs:.1f}%)")
    print(f"     ❌ Non faisables : {infeasible_with_alloc} ({100*infeasible_with_alloc/total_ofs:.1f}%)")
    print()

    # Différence
    diff_feasible = feasible_with_alloc - feasible_no_alloc
    print(f"   📈 Différence : {diff_feasible:+d} OFs faisables supplémentaires")
    print()

    # Composants en rupture
    missing_no_alloc = aggregate_missing_components(results_no_alloc)
    missing_with_alloc = aggregate_missing_components(results_with_alloc)

    print("\n" + "-"*80)
    print("COMPOSANTS EN RUPTURE (SANS allocation virtuelle)")
    print("-"*80 + "\n")

    if missing_no_alloc:
        print(f"   {'Article':<15} | {'Quantité manquante':>20}")
        print(f"   {'-'*15}-|-{'-'*20}")
        for article, qte in list(missing_no_alloc.items())[:20]:
            print(f"   {article:<15} | {qte:>20,}")

        if len(missing_no_alloc) > 20:
            print(f"   ... et {len(missing_no_alloc) - 20} autres articles")
    else:
        print("   ✅ Aucune rupture !")

    print("\n" + "-"*80)
    print("COMPOSANTS EN RUPTURE (AVEC allocation virtuelle)")
    print("-"*80 + "\n")

    if missing_with_alloc:
        print(f"   {'Article':<15} | {'Quantité manquante':>20}")
        print(f"   {'-'*15}-|-{'-'*20}")
        for article, qte in list(missing_with_alloc.items())[:20]:
            print(f"   {article:<15} | {qte:>20,}")

        if len(missing_with_alloc) > 20:
            print(f"   ... et {len(missing_with_alloc) - 20} autres articles")
    else:
        print("   ✅ Aucune rupture !")

    print()

    # OFs qui changent de statut
    print("\n" + "-"*80)
    print("OFs DONT LE STATUT A CHANGÉ")
    print("-"*80 + "\n")

    changed_to_feasible = []
    changed_to_infeasible = []

    for of_num in results_no_alloc.keys():
        feasible_no = results_no_alloc[of_num].feasible
        feasible_with = results_with_alloc[of_num].feasible

        if not feasible_no and feasible_with:
            changed_to_feasible.append(of_num)
        elif feasible_no and not feasible_with:
            changed_to_infeasible.append(of_num)

    if changed_to_feasible:
        print(f"   ✅ Devenus faisables ({len(changed_to_feasible)}) :")
        for of_num in changed_to_feasible[:10]:
            print(f"      {of_num}")
        if len(changed_to_feasible) > 10:
            print(f"      ... et {len(changed_to_feasible) - 10} autres")
        print()

    if changed_to_infeasible:
        print(f"   ❌ Devenus non faisables ({len(changed_to_infeasible)}) :")
        for of_num in changed_to_infeasible[:10]:
            print(f"      {of_num}")
        if len(changed_to_infeasible) > 10:
            print(f"      ... et {len(changed_to_infeasible) - 10} autres")
        print()

    if not changed_to_feasible and not changed_to_infeasible:
        print("   ℹ️  Aucun changement de statut")
        print()


def main():
    """Fonction principale."""
    print("\n" + "="*80)
    print("COMPARAISON : SANS vs AVEC allocation virtuelle")
    print("="*80 + "\n")

    # Charger les données
    print("⏳ Chargement des données...")
    loader = DataLoader("data")
    loader.load_all()
    print(f"   ✅ {len(loader.ofs)} OFs chargés")
    print(f"   ✅ {len(loader.commandes_clients)} commandes chargées")
    print()

    # Exécuter les deux vérifications
    results_no_alloc = run_verification_without_virtual_allocation(loader)
    results_with_alloc = run_verification_with_virtual_allocation(loader)

    # Comparer
    compare_results(results_no_alloc, results_with_alloc)

    print("\n" + "="*80)
    print("✅ Comparaison terminée")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
