# Agent IA logistique — VRP avec fenêtres horaires (ENSA Safi)

## Installation
```
pip install -r requirements.txt
```

## Utilisation
| Commande | Effet |
|---|---|
| `python vrp_solver.py` | Résout le problème (3 véhicules × 50 colis) et écrit `output/` |
| `python vrp_solver.py --vehicles 4 --capacity 40 --weights 1,2,5 --strength 0.02` | Paramètres personnalisés |
| `streamlit run app.py` | Interface graphique (paramètres, tableau de données éditable, carte, contrôles) |
| `python api.py` | API pour n8n (`POST /solve`, `GET /map`, `GET /result`, `GET /health`) |

## Contenu
- `data/clients.csv` : dépôt + 20 clients (Tableau 1)
- `vrp_solver.py` : moteur OR-Tools (capacité, fenêtres horaires, priorités)
- `app.py`, `api.py` : interface et API
- `n8n_workflow.json` : workflow n8n à importer
- `schema_workflow_n8n.png`, `rapport.md` / `rapport.docx` : schéma et rapport (parties 1, 2, 5, 6)
- `output/` : `carte_tournees.png`, `resultat.json`, `rapport_resultats.txt`, `matrice_distances.csv`

## Test rapide (test d'un cas infaisable)
`python vrp_solver.py --vehicles 2` : la capacité (100) est inférieure à la demande (118) ; les clients les moins prioritaires sont abandonnés et signalés.
