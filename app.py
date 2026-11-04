# -*- coding: utf-8 -*-
"""
Application Streamlit - Agent IA logistique (VRPTW)
Lancer :  streamlit run app.py
"""
import pandas as pd
import streamlit as st

from vrp_solver import (DEFAULT_DATA, distance_matrix, format_report, load_clients,
                        plot_routes, solve)

st.set_page_config(page_title="Agent IA VRP - VPR Logistics", layout="wide")
st.title("🚚 Agent IA logistique — Optimisation de tournées (VRPTW)")
st.caption("ENSA Safi · Logistique industrielle · Génie Aéronautique et Technologies de l'Espace")

# ---------------- Paramètres utilisateur (Partie 3, point 2) ----------------
with st.sidebar:
    st.header("Paramètres")
    nb_veh = st.number_input("Nombre de véhicules", 1, 10, 3)
    cap = st.number_input("Capacité par véhicule (colis)", 1, 500, 50)
    st.subheader("Pondérations de priorité")
    w1 = st.slider("Priorité 1 (faible)", 0.0, 10.0, 1.0, 0.5)
    w2 = st.slider("Priorité 2 (moyenne)", 0.0, 10.0, 2.0, 0.5)
    w3 = st.slider("Priorité 3 (urgente)", 0.0, 10.0, 3.0, 0.5)
    strength = st.slider("Influence des priorités sur la tournée", 0.0, 0.1, 0.01, 0.005,
                         help="0 = priorités ignorées (distance pure). Plus c'est grand, plus les clients urgents sont servis tôt.")
    use_tw = st.checkbox("Respecter les fenêtres horaires", True)
    tlim = st.slider("Temps de recherche (s)", 2, 60, 10)
    run = st.button("▶ Lancer l'optimisation", type="primary", use_container_width=True)

# ---------------- Données (éditables) ----------------
st.subheader("Données du dépôt et des 20 clients (modifiables)")
base = pd.DataFrame(load_clients(DEFAULT_DATA))
df = st.data_editor(base, use_container_width=True, hide_index=True, num_rows="fixed")
clients = df.to_dict("records")
for c in clients:
    for k in ("id", "demande", "service", "debut", "fin", "priorite"):
        c[k] = int(c[k])

with st.expander("Matrice des distances (calculée automatiquement, formule euclidienne)"):
    dm = distance_matrix(clients)
    ids = [c["id"] for c in clients]
    st.dataframe(pd.DataFrame(dm, index=ids, columns=ids).round(2), use_container_width=True)

# ---------------- Résolution + résultats ----------------
if run:
    with st.spinner("Optimisation en cours (OR-Tools)…"):
        res = solve(clients, num_vehicles=int(nb_veh), capacity=int(cap),
                    priority_weights={1: w1, 2: w2, 3: w3}, priority_strength=strength,
                    time_limit=int(tlim), enforce_time_windows=use_tw)
    if not res["solution_trouvee"]:
        st.error(res.get("message", "Aucune solution."))
        st.stop()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Distance totale", f"{res['distance_totale']:.2f} min")
    c2.metric("Véhicules utilisés", sum(r["utilise"] for r in res["routes"]))
    c3.metric("Demande / capacité", f"{res['demande_totale']} / {res['capacite_totale']}")
    ok = res["controles"]["toutes_contraintes_ok"]
    c4.metric("Contraintes", "✅ respectées" if ok else "⚠ violées")

    st.subheader("Tournées optimisées")
    rows = [{
        "Véhicule": r["vehicule"],
        "Tournée": " → ".join(map(str, r["sequence"])),
        "Distance (min)": round(r["distance"], 2),
        "Charge": f"{r['charge']}/{r['capacite']}",
        "Taux de charge": f"{100 * r['charge'] / r['capacite']:.0f} %",
        "Départ": round(r["depart"]), "Retour": round(r["retour"]),
    } for r in res["routes"]]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

           import os; os.makedirs("output", exist_ok=True)
  path = plot_routes(res, clients, "output/carte_tournees.png")
    st.image(path, use_container_width=True)

    st.subheader("Contrôle des contraintes")
    for k, label in [("chaque_client_une_fois", "Chaque client visité une seule fois"),
                     ("debut_fin_depot", "Tournées début/fin au dépôt"),
                     ("capacite_respectee", "Capacité respectée"),
                     ("fenetres_respectees", "Fenêtres horaires respectées"),
                     ("tous_clients_servis", "Tous les clients servis")]:
        st.write(("✅ " if res["controles"][k] else "❌ ") + label)
    for d in res["controles"]["details"]:
        st.warning(d)

    with st.expander("Détail des arrêts (arrivée, attente, service)"):
        stops = [{"Véhicule": r["vehicule"], **{k: s[k] for k in ("nom", "priorite", "arrivee", "attente", "debut_service", "fin_service", "a_l_heure")}}
                 for r in res["routes"] for s in r["arrets"]]
        st.dataframe(pd.DataFrame(stops), use_container_width=True, hide_index=True)
    st.download_button("⬇ Rapport texte", format_report(res), "rapport_resultats.txt")
else:
    st.info("Réglez les paramètres dans la barre latérale puis cliquez sur « Lancer l'optimisation ».")
