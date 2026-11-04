# -*- coding: utf-8 -*-
"""
API Flask - appelée par le workflow n8n (Partie 6)
Lancer :  python api.py      (écoute sur http://0.0.0.0:5000)

  GET  /health            -> {"status": "ok"}
  POST /solve             -> lance le VRPTW, retourne le JSON des résultats
        corps JSON (tous les champs sont optionnels) :
        {"vehicles": 3, "capacity": 50, "weights": [1,2,3], "strength": 0.01,
         "time_limit": 10, "time_windows": true}
  GET  /map               -> dernière carte des tournées (PNG)
  GET  /result            -> dernier résultat JSON
"""
from pathlib import Path

from flask import Flask, jsonify, request, send_file

from vrp_solver import DEFAULT_OUT, run_all

app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.post("/solve")
def solve_route():
    p = request.get_json(silent=True) or {}
    w = p.get("weights", [1, 2, 3])
    res = run_all(
        num_vehicles=int(p.get("vehicles", 3)),
        capacity=int(p.get("capacity", 50)),
        priority_weights={1: float(w[0]), 2: float(w[1]), 3: float(w[2])},
        priority_strength=float(p.get("strength", 0.01)),
        time_limit=int(p.get("time_limit", 10)),
        enforce_time_windows=bool(p.get("time_windows", True)),
    )
    # réponse allégée et facile à exploiter dans n8n
    if not res["solution_trouvee"]:
        return jsonify(res), 200
    summary = {
        "statut": res["statut"],
        "distance_totale": res["distance_totale"],
        "toutes_contraintes_ok": res["controles"]["toutes_contraintes_ok"],
        "controles": res["controles"],
        "clients_non_servis": res["clients_non_servis"],
        "vehicules": [
            {"vehicule": r["vehicule"], "tournee": r["sequence"], "distance": round(r["distance"], 2),
             "charge": r["charge"], "capacite": r["capacite"], "depart": r["depart"], "retour": r["retour"]}
            for r in res["routes"]
        ],
        "resume_texte": res["resume_texte"],
        "solution_trouvee": True,
        "carte_url": request.host_url.rstrip("/") + "/map",
    }
    return jsonify(summary)


@app.get("/map")
def get_map():
    f = Path(DEFAULT_OUT) / "carte_tournees.png"
    if not f.exists():
        return jsonify(error="Aucune carte : appelez d'abord POST /solve"), 404
    return send_file(f, mimetype="image/png")


@app.get("/result")
def get_result():
    f = Path(DEFAULT_OUT) / "resultat.json"
    if not f.exists():
        return jsonify(error="Aucun résultat"), 404
    return send_file(f, mimetype="application/json")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
