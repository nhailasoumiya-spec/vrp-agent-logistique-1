#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VRPTW Logistics Agent - moteur d'optimisation de tournées (OR-Tools)
=====================================================================
Devoir libre - Logistique industrielle - ENSA Safi (Pr. SALMI Houda)

Problème : Vehicle Routing Problem with Time Windows (VRPTW)
  - 1 dépôt (25, 25) + 20 clients
  - flotte de véhicules identiques (par défaut 3 x 50 colis)
  - fenêtres horaires, temps de service, priorités (1 = faible, 3 = urgente)

Utilisation en ligne de commande :
    python vrp_solver.py --vehicles 3 --capacity 50 --weights 1,2,3 --time-limit 10

Utilisation en bibliothèque :
    from vrp_solver import load_clients, solve, plot_routes
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import time
from pathlib import Path

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

# --------------------------------------------------------------------------
# Constantes
# --------------------------------------------------------------------------
TIME_SCALE = 100          # OR-Tools travaille en entiers : 1 minute = 100 unités
COST_K = 100              # facteur d'échelle du coût (distance) vs pénalité de priorité
HORIZON = 1440            # horizon de planification (minutes) = 24 h
TOL = 0.05                # tolérance numérique (min) due aux arrondis entiers
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA = BASE_DIR / "data" / "clients.csv"
DEFAULT_OUT = BASE_DIR / "output"


# --------------------------------------------------------------------------
# 1. Lecture des données et matrice des distances
# --------------------------------------------------------------------------
def load_clients(path: str | os.PathLike = DEFAULT_DATA) -> list[dict]:
    """Lit le CSV (dépôt = id 0 + 20 clients) -> liste de dictionnaires."""
    clients = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            clients.append(
                {
                    "id": int(r["id"]),
                    "nom": r["nom"],
                    "x": float(r["x"]),
                    "y": float(r["y"]),
                    "demande": int(r["demande"]),
                    "service": int(r["service"]),
                    "debut": int(r["debut"]),
                    "fin": int(r["fin"]),
                    "priorite": int(r["priorite"]),
                }
            )
    clients.sort(key=lambda c: c["id"])
    return clients


def distance_matrix(clients: list[dict]) -> list[list[float]]:
    """Matrice euclidienne D_ij = sqrt((xi-xj)^2 + (yi-yj)^2) (en minutes)."""
    return [
        [math.hypot(a["x"] - b["x"], a["y"] - b["y"]) for b in clients] for a in clients
    ]


def save_matrix_csv(clients: list[dict], dm: list[list[float]], path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["De\\Vers"] + [c["id"] for c in clients])
        for c, row in zip(clients, dm):
            w.writerow([c["id"]] + [f"{d:.2f}" for d in row])


# --------------------------------------------------------------------------
# 2. Simulation / vérification indépendante d'une tournée
# --------------------------------------------------------------------------
def simulate_route(seq: list[int], clients: list[dict], dm, depart: float = 0.0) -> dict:
    """Rejoue une tournée (dépôt -> clients -> dépôt) à partir de l'heure `depart`."""
    t = depart
    load = 0
    dist = 0.0
    stops = []
    ret = depart
    for a, b in zip(seq[:-1], seq[1:]):
        d = dm[a][b]
        dist += d
        arr = t + d
        if b == seq[-1] and b == 0 and len(stops) == len(seq) - 2:
            ret = arr
            break
        c = clients[b]
        start = max(arr, c["debut"])
        end = start + c["service"]
        load += c["demande"]
        stops.append(
            {
                "id": b,
                "nom": c["nom"],
                "priorite": c["priorite"],
                "demande": c["demande"],
                "charge_cumulee": load,
                "arrivee": round(arr, 2),
                "attente": round(start - arr, 2),
                "debut_service": round(start, 2),
                "fin_service": round(end, 2),
                "fenetre": [c["debut"], c["fin"]],
                "a_l_heure": start <= c["fin"] + TOL,
            }
        )
        t = end
    return {
        "depart": round(depart, 2),
        "retour": round(ret, 2),
        "duree": round(ret - depart, 2),
        "distance": dist,
        "charge": load,
        "arrets": stops,
    }


def build_route(seq, clients, dm) -> dict:
    """Simule la tournée à t=0, puis retarde le départ pour supprimer l'attente initiale."""
    sim = simulate_route(seq, clients, dm, 0.0)
    if sim["arrets"] and sim["arrets"][0]["attente"] > 0:
        sim = simulate_route(seq, clients, dm, sim["arrets"][0]["attente"])
    return sim


def verify_solution(clients, dm, routes, capacities, dropped, enforce_tw=True) -> dict:
    """Contrôle indépendant du solveur : on recalcule tout à partir des séquences."""
    n_clients = len(clients) - 1
    details = []

    # a) chaque client servi exactement une fois (ou explicitement non servi)
    count = {i: 0 for i in range(1, n_clients + 1)}
    for r in routes:
        for k in r["sequence"][1:-1]:
            count[k] += 1
    once_ok = all(
        (count[i] == 1 and i not in dropped) or (count[i] == 0 and i in dropped)
        for i in count
    )
    for i, c in count.items():
        if c > 1:
            details.append(f"Client {i} visité {c} fois")
        if c == 0 and i not in dropped:
            details.append(f"Client {i} jamais visité")

    # b) début et fin au dépôt
    depot_ok = all(r["sequence"][0] == 0 and r["sequence"][-1] == 0 for r in routes)
    if not depot_ok:
        details.append("Une tournée ne commence/finit pas au dépôt")

    # c) capacité
    cap_ok = True
    for r, cap in zip(routes, capacities):
        if r["charge"] > cap:
            cap_ok = False
            details.append(f"Véhicule {r['vehicule']} : charge {r['charge']} > {cap}")

    # d) fenêtres horaires + retour au dépôt avant la fermeture
    tw_ok = True
    for r in routes:
        for s in r["arrets"]:
            if not s["a_l_heure"]:
                tw_ok = False
                details.append(
                    f"Client {s['id']} servi à {s['debut_service']:.0f} min "
                    f"(fenêtre {s['fenetre'][0]}-{s['fenetre'][1]})"
                )
        if r["retour"] > clients[0]["fin"] + TOL:
            tw_ok = False
            details.append(f"Véhicule {r['vehicule']} rentre trop tard ({r['retour']:.0f} min)")

    all_ok = once_ok and depot_ok and cap_ok and (tw_ok or not enforce_tw) and not dropped
    return {
        "chaque_client_une_fois": once_ok,
        "debut_fin_depot": depot_ok,
        "capacite_respectee": cap_ok,
        "fenetres_respectees": tw_ok,
        "tous_clients_servis": not dropped,
        "toutes_contraintes_ok": all_ok,
        "details": details,
    }


# --------------------------------------------------------------------------
# 3. Solveur OR-Tools (VRPTW + priorités)
# --------------------------------------------------------------------------
_STATUS = {
    0: "NOT_SOLVED",
    1: "SUCCESS",
    2: "PARTIAL_SUCCESS_LOCAL_OPTIMUM_NOT_REACHED",
    3: "FAIL",
    4: "FAIL_TIMEOUT",
    5: "INVALID",
    6: "INFEASIBLE",
    7: "OPTIMAL",
}


def solve(
    clients: list[dict],
    num_vehicles: int = 3,
    capacity: int | list[int] = 50,
    priority_weights: dict | None = None,
    priority_strength: float = 0.01,
    time_limit: int = 10,
    enforce_time_windows: bool = True,
    allow_drop: bool = True,
) -> dict:
    """
    Résout le VRPTW.

    Objectif : minimiser  distance totale
                         + pénalité de retard pondérée par la priorité
                         + pénalité (très forte) de client non servi.

    priority_weights  : {1: w1, 2: w2, 3: w3}  pondération saisie par l'utilisateur
    priority_strength : intensité de l'effet priorité (0 = priorité ignorée)
    """
    t0 = time.time()
    pw = {1: 1.0, 2: 2.0, 3: 3.0}
    if priority_weights:
        pw.update({int(k): float(v) for k, v in priority_weights.items()})

    n = len(clients)
    dm = distance_matrix(clients)
    dmi = [[int(round(d * TIME_SCALE)) for d in row] for row in dm]
    caps = [int(capacity)] * num_vehicles if isinstance(capacity, (int, float)) else [int(c) for c in capacity]
    if len(caps) != num_vehicles:
        raise ValueError("La liste des capacités doit contenir une valeur par véhicule.")

    manager = pywrapcp.RoutingIndexManager(n, num_vehicles, 0)
    routing = pywrapcp.RoutingModel(manager)

    # --- coût = distance
    def dist_cb(i, j):
        return dmi[manager.IndexToNode(i)][manager.IndexToNode(j)] * COST_K

    routing.SetArcCostEvaluatorOfAllVehicles(routing.RegisterTransitCallback(dist_cb))

    # --- contrainte de capacité
    def demand_cb(i):
        return clients[manager.IndexToNode(i)]["demande"]

    routing.AddDimensionWithVehicleCapacity(
        routing.RegisterUnaryTransitCallback(demand_cb), 0, caps, True, "Capacite"
    )

    # --- dimension temps = déplacement + service au noeud de départ
    def time_cb(i, j):
        a, b = manager.IndexToNode(i), manager.IndexToNode(j)
        return dmi[a][b] + clients[a]["service"] * TIME_SCALE

    H = HORIZON * TIME_SCALE
    routing.AddDimension(routing.RegisterTransitCallback(time_cb), H, H, True, "Temps")
    time_dim = routing.GetDimensionOrDie("Temps")

    # --- fenêtres horaires clients
    if enforce_time_windows:
        for c in clients[1:]:
            idx = manager.NodeToIndex(c["id"])
            time_dim.CumulVar(idx).SetRange(c["debut"] * TIME_SCALE, min(c["fin"], HORIZON) * TIME_SCALE)
    # --- fenêtre du dépôt (ouverture / fermeture)
    dep = clients[0]
    for v in range(num_vehicles):
        time_dim.CumulVar(routing.Start(v)).SetRange(dep["debut"] * TIME_SCALE, dep["fin"] * TIME_SCALE)
        time_dim.CumulVar(routing.End(v)).SetRange(dep["debut"] * TIME_SCALE, dep["fin"] * TIME_SCALE)
        routing.AddVariableMinimizedByFinalizer(time_dim.CumulVar(routing.End(v)))

    # --- priorités : plus la priorité est forte, plus le retard de service est coûteux
    for c in clients[1:]:
        idx = manager.NodeToIndex(c["id"])
        w = pw.get(c["priorite"], 1.0)
        coef = int(round(100 * priority_strength * w))
        if coef > 0:
            target = (c["debut"] if enforce_time_windows else 0) * TIME_SCALE
            time_dim.SetCumulVarSoftUpperBound(idx, target, coef)
        # client optionnel : ne peut être abandonné qu'en dernier recours, urgents en dernier
        if allow_drop:
            routing.AddDisjunction([idx], int(10**8 * max(w, 1.0)))

    # --- recherche : plusieurs stratégies de solution initiale en secours
    solution = None
    used = None
    for strat in (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC,
        routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION,
        routing_enums_pb2.FirstSolutionStrategy.SAVINGS,
    ):
        params = pywrapcp.DefaultRoutingSearchParameters()
        params.first_solution_strategy = strat
        params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        params.time_limit.FromSeconds(int(time_limit))
        solution = routing.SolveWithParameters(params)
        if solution:
            used = routing_enums_pb2.FirstSolutionStrategy.Value.Name(strat) if hasattr(
                routing_enums_pb2.FirstSolutionStrategy, "Value") else str(strat)
            break

    result = {
        "parametres": {
            "nb_vehicules": num_vehicles,
            "capacites": caps,
            "poids_priorite": pw,
            "intensite_priorite": priority_strength,
            "fenetres_horaires_actives": enforce_time_windows,
            "temps_limite_s": time_limit,
        },
        "statut": _STATUS.get(routing.status(), str(routing.status())),
        "solution_trouvee": bool(solution),
    }
    if not solution:
        result["message"] = "Aucune solution trouvée (problème infaisable avec ces paramètres)."
        return result

    # --- extraction
    routes = []
    served = set()
    for v in range(num_vehicles):
        idx = routing.Start(v)
        seq = [0]
        while not routing.IsEnd(idx):
            idx = solution.Value(routing.NextVar(idx))
            seq.append(manager.IndexToNode(idx))
        served.update(seq[1:-1])
        sim = build_route(seq, clients, dm)
        routes.append(
            {
                "vehicule": v + 1,
                "capacite": caps[v],
                "utilise": len(seq) > 2,
                "sequence": seq,
                "noms": [clients[k]["nom"] for k in seq],
                **sim,
            }
        )
    dropped = sorted(set(range(1, n)) - served)
    checks = verify_solution(clients, dm, routes, caps, dropped, enforce_time_windows)

    total = sum(r["distance"] for r in routes)
    # analyse par niveau de priorité (heure moyenne de début de service)
    prio_stats = {}
    for r in routes:
        for s in r["arrets"]:
            prio_stats.setdefault(s["priorite"], []).append(s["debut_service"])
    prio_summary = {
        p: {"nb_clients": len(v), "debut_service_moyen": round(sum(v) / len(v), 1)}
        for p, v in sorted(prio_stats.items())
    }
    result.update(
        {
            "strategie_initiale": used,
            "distance_totale": round(total, 2),
            "routes": routes,
            "clients_non_servis": dropped,
            "controles": checks,
            "analyse_priorites": prio_summary,
            "temps_calcul_s": round(time.time() - t0, 2),
            "demande_totale": sum(c["demande"] for c in clients),
            "capacite_totale": sum(caps),
        }
    )
    return result


# --------------------------------------------------------------------------
# 4. Visualisation (Partie 4)
# --------------------------------------------------------------------------
def plot_routes(result: dict, clients: list[dict], path: str | os.PathLike) -> str:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    routes = [r for r in result["routes"] if r["utilise"]]
    cmap = plt.get_cmap("tab10")
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(16, 7.2), gridspec_kw={"width_ratios": [2.3, 1]})

    handles = []
    for k, r in enumerate(routes):
        col = cmap(k % 10)
        pts = [(clients[i]["x"], clients[i]["y"]) for i in r["sequence"]]
        for a, b in zip(pts[:-1], pts[1:]):
            ax.annotate("", xy=b, xytext=a, arrowprops=dict(arrowstyle="->", color=col, lw=1.8, shrinkA=4, shrinkB=4))
        for i in r["sequence"][1:-1]:
            c = clients[i]
            tw = c["debut"] > 0 or c["fin"] < HORIZON
            ax.scatter(c["x"], c["y"], s=95, color=col, marker="s" if tw else "o", edgecolor="black", zorder=3)
            ax.annotate(str(i), (c["x"], c["y"]), textcoords="offset points", xytext=(6, 6), fontsize=9, weight="bold")
        handles.append(
            Line2D([0], [0], color=col, lw=3,
                   label=f"Véhicule {r['vehicule']} : {r['distance']:.1f} min — charge {r['charge']}/{r['capacite']}")
        )
    for i in result.get("clients_non_servis", []):
        c = clients[i]
        ax.scatter(c["x"], c["y"], s=110, color="grey", marker="X", zorder=3)
        ax.annotate(str(i), (c["x"], c["y"]), textcoords="offset points", xytext=(6, 6), fontsize=9)
    ax.scatter(clients[0]["x"], clients[0]["y"], s=380, color="gold", marker="*", edgecolor="black", zorder=4)
    handles.append(Line2D([0], [0], marker="*", color="w", markerfacecolor="gold", markeredgecolor="black", markersize=16, label="Dépôt"))
    handles.append(Line2D([0], [0], marker="o", color="w", markerfacecolor="lightgrey", markeredgecolor="black", markersize=9, label="Client sans fenêtre"))
    handles.append(Line2D([0], [0], marker="s", color="w", markerfacecolor="lightgrey", markeredgecolor="black", markersize=9, label="Client avec fenêtre horaire"))
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=2, fontsize=9, frameon=False)
    ax.set_title(f"Tournées optimisées — distance totale = {result['distance_totale']:.2f} min", fontsize=13, weight="bold")
    ax.set_xlabel("x"); ax.set_ylabel("y"); ax.grid(alpha=0.25); ax.set_aspect("equal", adjustable="datalim")

    # barres : distance par véhicule
    labels = [f"V{r['vehicule']}" for r in routes]
    bars = bx.bar(labels, [r["distance"] for r in routes], color=[cmap(k % 10) for k in range(len(routes))], edgecolor="black")
    for b, r in zip(bars, routes):
        bx.text(b.get_x() + b.get_width() / 2, b.get_height() + 1, f"{r['distance']:.1f}\n({r['charge']}/{r['capacite']} colis)", ha="center", fontsize=9)
    bx.set_ylim(0, max(r["distance"] for r in routes) * 1.25)
    bx.set_title("Distance parcourue par véhicule", fontsize=12, weight="bold")
    bx.set_ylabel("minutes"); bx.grid(axis="y", alpha=0.25)

    fig.tight_layout()
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return str(path)


# --------------------------------------------------------------------------
# 5. Rapport texte (console / e-mail n8n)
# --------------------------------------------------------------------------
def format_report(result: dict) -> str:
    if not result.get("solution_trouvee"):
        return "AUCUNE SOLUTION : " + result.get("message", "")
    L = []
    L.append("=" * 64)
    L.append("RÉSULTATS - OPTIMISATION DE TOURNÉES (VRPTW)")
    L.append("=" * 64)
    L.append(f"Statut solveur : {result['statut']}  |  Temps de calcul : {result['temps_calcul_s']} s")
    L.append(f"Distance totale : {result['distance_totale']:.2f} min")
    L.append(f"Demande totale : {result['demande_totale']} colis / capacité flotte : {result['capacite_totale']}")
    for r in result["routes"]:
        L.append("")
        if not r["utilise"]:
            L.append(f"Véhicule {r['vehicule']} : non utilisé")
            continue
        L.append(f"Véhicule {r['vehicule']} : " + " -> ".join(map(str, r["sequence"])))
        L.append(f"   distance {r['distance']:.2f} min | charge {r['charge']}/{r['capacite']} | "
                 f"départ {r['depart']:.0f} min | retour {r['retour']:.0f} min | durée {r['duree']:.0f} min")
        for s in r["arrets"]:
            tw = "" if s["fenetre"] == [0, 1440] else f" fenêtre {s['fenetre'][0]}-{s['fenetre'][1]}"
            L.append(f"   - {s['nom']:<10} P{s['priorite']} arrivée {s['arrivee']:>7.1f} attente {s['attente']:>5.1f} "
                     f"service {s['debut_service']:>7.1f}->{s['fin_service']:>7.1f}{tw} {'OK' if s['a_l_heure'] else 'RETARD'}")
    c = result["controles"]
    L.append("")
    L.append("CONTRÔLE DES CONTRAINTES")
    for key, label in [
        ("chaque_client_une_fois", "Chaque client visité une seule fois"),
        ("debut_fin_depot", "Chaque tournée commence et finit au dépôt"),
        ("capacite_respectee", "Capacité des véhicules respectée"),
        ("fenetres_respectees", "Fenêtres horaires respectées"),
        ("tous_clients_servis", "Tous les clients servis"),
    ]:
        L.append(f"   [{'OK' if c[key] else 'NON'}] {label}")
    for d in c["details"]:
        L.append(f"   ! {d}")
    L.append(f"=> Toutes contraintes respectées : {'OUI' if c['toutes_contraintes_ok'] else 'NON'}")
    L.append("")
    L.append("PRIORITÉS (début de service moyen, min) : " + ", ".join(
        f"P{p}: {v['debut_service_moyen']} ({v['nb_clients']} clients)" for p, v in result["analyse_priorites"].items()))
    return "\n".join(L)


# --------------------------------------------------------------------------
# 6. Exécution complète : solve + fichiers de sortie
# --------------------------------------------------------------------------
def run_all(data_path=DEFAULT_DATA, out_dir=DEFAULT_OUT, **kwargs) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    clients = load_clients(data_path)
    result = solve(clients, **kwargs)
    save_matrix_csv(clients, distance_matrix(clients), out / "matrice_distances.csv")
    result["resume_texte"] = format_report(result)
    if result["solution_trouvee"]:
        plot_routes(result, clients, out / "carte_tournees.png")
        result["carte"] = "carte_tournees.png"
    with open(out / "resultat.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open(out / "rapport_resultats.txt", "w", encoding="utf-8") as f:
        f.write(result["resume_texte"])
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="Agent VRPTW - OR-Tools")
    ap.add_argument("--data", default=str(DEFAULT_DATA), help="fichier CSV clients")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="dossier de sortie")
    ap.add_argument("--vehicles", type=int, default=3, help="nombre de véhicules")
    ap.add_argument("--capacity", type=int, default=50, help="capacité par véhicule (colis)")
    ap.add_argument("--weights", default="1,2,3", help="poids des priorités 1,2,3 (ex: 1,2,3)")
    ap.add_argument("--strength", type=float, default=0.01, help="intensité de l'effet priorité (0 = ignoré)")
    ap.add_argument("--time-limit", type=int, default=10, help="durée de recherche (s)")
    ap.add_argument("--no-tw", action="store_true", help="ignorer les fenêtres horaires")
    args = ap.parse_args()
    w = [float(x) for x in args.weights.split(",")]
    res = run_all(
        data_path=args.data,
        out_dir=args.out,
        num_vehicles=args.vehicles,
        capacity=args.capacity,
        priority_weights={1: w[0], 2: w[1], 3: w[2]},
        priority_strength=args.strength,
        time_limit=args.time_limit,
        enforce_time_windows=not args.no_tw,
    )
    print(res["resume_texte"])
    print(f"\nFichiers générés dans : {args.out}")


if __name__ == "__main__":
    main()
