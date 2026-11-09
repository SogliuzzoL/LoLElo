# LoLElo

Bot Discord de classement pour des parties personnalisées de League of Legends : enregistrement des joueurs, saisie des matchs, classement et génération d'équipes équilibrées.

Deux implémentations du rating coexistent dans le dépôt :

- `main.py` — rating **TrueSkill** (`mu` initial 25, `sigma` 8.33) avec commandes slash et classement illustré par un graphique matplotlib ;
- `elo.py` — rating **Elo** classique (base 1000, `K = 32`) avec les mêmes opérations.

## Commandes

| Version | Commande | Effet |
|---|---|---|
| TrueSkill | `/add_player` | Ajoute un ou plusieurs joueurs |
| TrueSkill | `/match` | Enregistre un match entre deux équipes |
| TrueSkill | `/team` | Tire deux équipes équilibrées |
| TrueSkill | `/top` | Affiche le classement avec boutons interactifs |
| Elo | `/elo_add`, `/elo_match`, `/elo_teams`, `/elo_top` | Équivalents en Elo |

## Configuration

Copier `config.exemple.json` vers `config.json` puis renseigner le token du bot :

```json
{
  "token": "TON_TOKEN_ICI"
}
```

## Lancer

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Données

Les classements sont persistés dans des fichiers JSON locaux (`players.json` pour l'Elo, `trueskill.json` pour TrueSkill). Aucune base de données n'est utilisée.

## Limites

- Les fichiers JSON ne sont pas protégés contre les accès concurrents.
- Pas de tests automatisés.
- Le code suppose un unique serveur Discord et une pratique 1v1 ou par équipes fixes.
