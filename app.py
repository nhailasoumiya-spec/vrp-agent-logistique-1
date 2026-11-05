# -*- coding: utf-8 -*-
"""
Application Streamlit - Agent IA logistique (VRPTW)
Mise en page : bleu marine / bleu ciel
Lancer :  streamlit run app.py
"""
import os

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from matplotlib.colors import ListedColormap

from vrp_solver import (DEFAULT_DATA, distance_matrix, format_report, load_clients,
                        plot_routes, solve)

os.makedirs("output", exist_ok=True)
MAP_PATH = "output/carte_tournees.png"

# ---- palette de la carte : bleu marine / bleu ciel + couleurs d'accent bien distinctes
_PALETTE = ListedColormap(["#0B2545", "#4DA8DA", "#F28C28", "#2A9D8F", "#8E6BBF",
                           "#D64545", "#7A8B99", "#E9C46A", "#3D5A80", "#98C1D9"])
_orig_get_cmap = plt.get_cmap
plt.get_cmap = lambda name=None, *a, **k: _PALETTE if name == "tab10" else _orig_get_cmap(name, *a, **k)

st.set_page_config(page_title="Agent IA VRP | VPR Logistics", page_icon="🚚", layout="wide")

# ============================== STYLE (bleu marine / bleu ciel) ==============================
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, .stApp, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: #F4F8FC; color: #0B2545; }
#MainMenu, footer { visibility: hidden; }
.block-container { padding-top: 4rem; padding-bottom: 3rem; max-width: 1300px; }
[data-testid="stHeader"] { background: transparent; }

/* bannière */
.hero { background: linear-gradient(120deg, #0B2545 0%, #13518A 62%, #4DA8DA 135%);
        border-radius: 18px; padding: 30px 36px; margin-bottom: 24px;
        box-shadow: 0 10px 28px rgba(11,37,69,.28); }
.hero .badge { display: inline-block; background: rgba(141,202,230,.18); color: #BFE3F7;
        border: 1px solid rgba(141,202,230,.5); padding: 4px 14px; border-radius: 999px;
        font-size: .78rem; font-weight: 600; letter-spacing: .3px; }
.hero .title { color: #FFFFFF; font-size: 2.15rem; font-weight: 700; margin: 14px 0 4px 0; line-height: 1.2; }
.hero .subtitle { color: #CFE8F8; font-size: 1.02rem; margin: 0; }
.hero .chips { margin-top: 16px; }
.hero .chip { display: inline-block; background: #FFFFFF; color: #0B2545; font-size: .8rem;
        font-weight: 600; padding: 5px 12px; border-radius: 8px; margin-right: 8px; }

/* barre latérale */
[data-testid="stSidebar"] { background: #E3F0FB; border-right: 1px solid #C5DEF2; }
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 { color: #0B2545 !important; }
[data-testid="stSidebar"] label, [data-testid="stSidebar"] p { color: #0B2545; }

/* titres */
h2, h3 { color: #0B2545 !important; font-weight: 700 !important; }
.section { color: #0B2545; font-size: 1.15rem; font-weight: 700; margin: 6px 0 10px 0;
           padding-left: 12px; border-left: 5px solid #4DA8DA; }

/* cartes de chiffres clés */
[data-testid="stMetric"] { background: #FFFFFF; border: 1px solid #D6E8F7; border-left: 6px solid #4DA8DA;
        border-radius: 14px; padding: 16px 20px; box-shadow: 0 3px 10px rgba(11,37,69,.07); }
[data-testid="stMetricLabel"] p { color: #13518A !important; font-weight: 600; }
[data-testid="stMetricValue"] { color: #0B2545; font-weight: 700; font-size: 1.9rem; }

/* onglets */
[data-testid="stTab"] p { font-weight: 600; color: #13518A !important; font-size: 1rem; }
[data-testid="stTab"][aria-selected="true"] p { color: #0B2545 !important; }
[data-testid="stTab"][aria-selected="true"] > div:not([data-testid]) { filter: hue-rotate(205deg) saturate(.9); }

/* curseurs et cases à cocher : rouge par défaut -> bleu */
[data-testid="stSlider"] [role="group"] > div { filter: hue-rotate(205deg) saturate(.9) brightness(.9); }
[data-testid="stCheckbox"] label > div:first-of-type { filter: hue-rotate(205deg) saturate(.9) brightness(.9); }

/* boutons */
.stButton > button[kind="primary"], .stDownloadButton > button {
        background: linear-gradient(120deg, #0B2545, #13518A); color: #FFFFFF; border: none;
        border-radius: 10px; font-weight: 600; padding: .6rem 1rem; }
.stButton > button[kind="primary"]:hover, .stDownloadButton > button:hover {
        background: linear-gradient(120deg, #13518A, #4DA8DA); color: #FFFFFF; }

/* tableaux et expanders */
[data-testid="stDataFrame"], [data-testid="stDataEditor"] { border: 1px solid #D6E8F7; border-radius: 12px; overflow: hidden; }
[data-testid="stExpander"] { background: #FFFFFF; border: 1px solid #D6E8F7; border-radius: 12px; }

/* contrôle des contraintes */
.pill { display: block; background: #FFFFFF; border: 1px solid #D6E8F7; border-radius: 10px;
        padding: 10px 14px; margin-bottom: 8px; font-weight: 500; }
.pill.ok { border-left: 6px solid #2A9D8F; }
.pill.ko { border-left: 6px solid #D64545; }

.footer { text-align: center; color: #5B7A99; font-size: .82rem; margin-top: 42px;
          padding-top: 14px; border-top: 1px solid #D6E8F7; }
</style>
""",
    unsafe_allow_html=True,
)

# ============================== EN-TÊTE ==============================
st.markdown(
    """
<div class="hero">
  <span class="badge">ENSA Safi · Génie Aéronautique et Technologies de l'Espace</span>
  <div class="title">🚚 Agent IA logistique — Optimisation de tournées</div>
  <p class="subtitle">Vehicle Routing Problem avec fenêtres horaires (VRPTW) · Google OR-Tools · VPR Logistics</p>
  <div class="chips"><span class="chip">1 dépôt</span><span class="chip">20 clients</span>
  <span class="chip">Capacité · Fenêtres horaires · Priorités</span></div>
</div>
""",
    unsafe_allow_html=True,
)

# ============================== PARAMÈTRES ==============================
with st.sidebar:
    st.header("⚙️ Paramètres")
    nb_veh = st.number_input("Nombre de véhicules", 1, 10, 3)
    cap = st.number_input("Capacité par véhicule (colis)", 1, 500, 50)
    st.subheader("Pondérations de priorité")
    w1 = st.slider("Priorité 1 (faible)", 0.0, 10.0, 1.0, 0.5)
    w2 = st.slider("Priorité 2 (moyenne)", 0.0, 10.0, 2.0, 0.5)
    w3 = st.slider("Priorité 3 (urgente)", 0.0, 10.0, 3.0, 0.5)
    strength = st.slider("Influence des priorités", 0.0, 0.1, 0.01, 0.005,
                         help="0 = priorités ignorées (distance pure). Plus la valeur est grande, plus les clients urgents sont servis tôt.")
    use_tw = st.checkbox("Respecter les fenêtres horaires", True)
    tlim = st.slider("Temps de recherche (s)", 2, 60, 10)
    run = st.button("▶ Lancer l'optimisation", type="primary", width="stretch")

tab_res, tab_data, tab_about = st.tabs(["📊 Résultats", "🗂️ Données et distances", "ℹ️ À propos"])

# ============================== DONNÉES ==============================
with tab_data:
    st.markdown('<div class="section">Dépôt et 20 clients (modifiables)</div>', unsafe_allow_html=True)
    base = pd.DataFrame(load_clients(DEFAULT_DATA))
    df = st.data_editor(base, width="stretch", hide_index=True, num_rows="fixed")
    clients = df.to_dict("records")
    for c in clients:
        for k in ("id", "demande", "service", "debut", "fin", "priorite"):
            c[k] = int(c[k])
    with st.expander("Matrice des distances (formule euclidienne, en minutes)"):
        dm = distance_matrix(clients)
        ids = [c["id"] for c in clients]
        st.dataframe(pd.DataFrame(dm, index=ids, columns=ids).round(2), width="stretch")

# ============================== RÉSOLUTION ==============================
if run:
    with st.spinner("Optimisation en cours (OR-Tools)…"):
        res = solve(clients, num_vehicles=int(nb_veh), capacity=int(cap),
                    priority_weights={1: w1, 2: w2, 3: w3}, priority_strength=strength,
                    time_limit=int(tlim), enforce_time_windows=use_tw)
        if res["solution_trouvee"]:
            plot_routes(res, clients, MAP_PATH)
    st.session_state["res"] = res

# ============================== RÉSULTATS ==============================
with tab_res:
    res = st.session_state.get("res")
    if res is None:
        st.info("Réglez les paramètres dans la barre latérale, puis cliquez sur « ▶ Lancer l'optimisation ».")
    elif not res["solution_trouvee"]:
        st.error(res.get("message", "Aucune solution trouvée."))
    else:
        ok = res["controles"]["toutes_contraintes_ok"]
        used = sum(r["utilise"] for r in res["routes"])
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Distance totale", f"{res['distance_totale']:.2f} min")
        k2.metric("Véhicules utilisés", f"{used} / {len(res['routes'])}")
        k3.metric("Colis livrés / capacité", f"{res['demande_totale']} / {res['capacite_totale']}")
        k4.metric("Contraintes", "Respectées" if ok else "Violées")
        st.write("")

        t1, t2, t3, t4 = st.tabs(["Tournées", "Carte", "Contrôles", "Détail des arrêts"])

        with t1:
            st.markdown('<div class="section">Tournées optimisées</div>', unsafe_allow_html=True)
            rows = [{
                "Véhicule": f"V{r['vehicule']}",
                "Tournée": " → ".join(map(str, r["sequence"])),
                "Distance (min)": round(r["distance"], 2),
                "Charge": f"{r['charge']} / {r['capacite']}",
                "Taux de charge": f"{100 * r['charge'] / r['capacite']:.0f} %",
                "Départ (min)": round(r["depart"]),
                "Retour (min)": round(r["retour"]),
            } for r in res["routes"]]
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

        with t2:
            st.markdown('<div class="section">Carte des tournées et distance par véhicule</div>', unsafe_allow_html=True)
            st.image(MAP_PATH, width="stretch")
            with open(MAP_PATH, "rb") as f:
                st.download_button("⬇ Télécharger la carte (PNG)", f.read(), "carte_tournees.png", "image/png")

        with t3:
            st.markdown('<div class="section">Respect des contraintes</div>', unsafe_allow_html=True)
            for k, label in [("chaque_client_une_fois", "Chaque client visité une seule fois"),
                             ("debut_fin_depot", "Chaque tournée commence et finit au dépôt"),
                             ("capacite_respectee", "Capacité des véhicules respectée"),
                             ("fenetres_respectees", "Fenêtres horaires respectées"),
                             ("tous_clients_servis", "Tous les clients servis")]:
                good = res["controles"][k]
                st.markdown(f'<span class="pill {"ok" if good else "ko"}">{"✅" if good else "❌"} {label}</span>',
                            unsafe_allow_html=True)
            for d in res["controles"]["details"]:
                st.warning(d)
            st.markdown('<div class="section">Effet des priorités</div>', unsafe_allow_html=True)
            prio = pd.DataFrame([{"Priorité": p, "Clients": v["nb_clients"],
                                  "Début de service moyen (min)": v["debut_service_moyen"]}
                                 for p, v in res["analyse_priorites"].items()])
            st.dataframe(prio, width="stretch", hide_index=True)

        with t4:
            st.markdown('<div class="section">Arrivée, attente et service par client</div>', unsafe_allow_html=True)
            stops = [{"Véhicule": f"V{r['vehicule']}", "Client": s["nom"], "Priorité": s["priorite"],
                      "Arrivée": s["arrivee"], "Attente": s["attente"],
                      "Début service": s["debut_service"], "Fin service": s["fin_service"],
                      "Fenêtre": f"{s['fenetre'][0]}–{s['fenetre'][1]}",
                      "À l'heure": "✅" if s["a_l_heure"] else "❌"}
                     for r in res["routes"] for s in r["arrets"]]
            st.dataframe(pd.DataFrame(stops), width="stretch", hide_index=True)
            st.download_button("⬇ Rapport complet (texte)", format_report(res), "rapport_resultats.txt")

# ============================== À PROPOS ==============================
with tab_about:
    st.markdown('<div class="section">Fonctionnement</div>', unsafe_allow_html=True)
    st.markdown(
        """
- **Problème** : tournées de livraison de 3 véhicules identiques (50 colis) depuis un dépôt unique vers 20 clients.
- **Contraintes** : capacité des véhicules, fenêtres horaires, temps de service, priorités (1 = faible, 3 = urgente).
- **Méthode** : Google OR-Tools (solution initiale + recherche locale guidée). Les distances sont calculées par la formule euclidienne.
- **Contrôle** : les contraintes sont revérifiées indépendamment du solveur après chaque résolution.
"""
    )

st.markdown('<div class="footer">Devoir libre · Module Logistique industrielle · ENSA Safi · Pr. SALMI Houda</div>',
            unsafe_allow_html=True)
