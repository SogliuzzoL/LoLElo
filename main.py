import discord
from discord.ext import commands
from discord import app_commands
from typing import List
from trueskill import Rating, rate
import json
import os

# Chargement config
with open("config.json", "r") as f:
    config = json.load(f)

TOKEN = config["token"]
DATA_FILE = "trueskill.json"
MU = 25
SIGMA = 8.333

# JSON
def load_players():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_players(players):
    with open(DATA_FILE, "w") as f:
        json.dump(players, f, indent=2)

def register_player(players, name):
    key = name.lower()
    if key not in players:
        players[key] = {"mu": MU, "sigma": SIGMA, "nb_matchs": 0, "nb_win": 0, "display_name": name}

def process_match(players, team_a, team_b, winner):
    team_A = [Rating(mu=players[player]["mu"],sigma=players[player]["sigma"]) for player in team_a]
    team_B = [Rating(mu=players[player]["mu"],sigma=players[player]["sigma"]) for player in team_b]
    ranks = [0, 1] if winner == "A" else [1, 0]

    team_A, team_B = rate([team_A, team_B], ranks=ranks)

    for (player, rating) in zip(team_a, team_A):
        players[player]["mu"] = rating.mu
        players[player]["sigma"] = rating.sigma
        players[player]["nb_matchs"] += 1
        if winner == "A":
            players[player]["nb_win"] += 1

    for (player, rating) in zip(team_b, team_B):
        players[player]["mu"] = rating.mu
        players[player]["sigma"] = rating.sigma
        players[player]["nb_matchs"] += 1
        if winner == "B":
            players[player]["nb_win"] += 1



    # for p in team_a:
    #     exp = expected_score(players[p]["elo"], elo_b_avg)
    #     players[p]["elo"] = update_elo(players[p]["elo"], exp, result_a)
    #     players[p]["nb_matchs"] += 1

    # for p in team_b:
    #     exp = expected_score(players[p]["elo"], elo_a_avg)
    #     players[p]["elo"] = update_elo(players[p]["elo"], exp, result_b)
    #     players[p]["nb_matchs"] += 1

# Bot setup
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

@tree.command(name="add_player", description="Ajoute un ou plusieurs joueurs au classement.")
@app_commands.describe(joueurs="Noms des joueurs séparés par des espaces")
async def add_player(interaction: discord.Interaction, joueurs: str):
    players = load_players()
    noms = joueurs.split()
    for name in noms:
        register_player(players, name)
    save_players(players)
    await interaction.response.send_message(f"✅ Joueurs enregistrés : {', '.join(noms)}", ephemeral=True)

@tree.command(name="match", description="Enregistre un match entre deux équipes.")
@app_commands.describe(winner="Vainqueur (A ou B)", equipe_a="Liste des joueurs équipe A", equipe_b="Liste équipe B")
async def match(interaction: discord.Interaction, winner: str, equipe_a: str, equipe_b: str):
    players = load_players()
    team_a = [p.lower() for p in equipe_a.split()]
    team_b = [p.lower() for p in equipe_b.split()]
    winner = winner.upper()

    all_players = team_a + team_b
    for p in all_players:
        register_player(players, p)

    if winner not in ["A", "B"]:
        await interaction.response.send_message("❌ Le vainqueur doit être A ou B.", ephemeral=True)
        return

    # Sauvegarde des TrueSkill avant le match
    old_mu = {p: players[p]["mu"] for p in all_players}

    # Traitement du match
    process_match(players, team_a, team_b, winner)
    save_players(players)

    # Création du message public
    def format_change(p):
        old = old_mu[p]
        new = players[p]["mu"]
        diff = new - old
        signe = "➕" if diff >= 0 else "➖"
        return f"{p} : {old:.2f} → {new:.2f} ({signe}{abs(diff):.2f})"

    msg = f"🏆 **Match enregistré - Victoire équipe {winner}**\n\n"
    msg += "**Équipe A :**\n" + "\n".join([format_change(p) for p in team_a]) + "\n\n"
    msg += "**Équipe B :**\n" + "\n".join([format_change(p) for p in team_b])

    await interaction.response.send_message(msg)

@tree.command(name="top", description="Affiche le classement des joueurs par Elo.")
@app_commands.describe(top_n="Nombre de joueurs à afficher (par défaut 20)")
async def top(interaction: discord.Interaction, top_n: int = 20):
    players = load_players()
    if not players:
        await interaction.response.send_message("❌ Aucun joueur enregistré.", ephemeral=True)
        return

    sorted_players = sorted(players.items(), key=lambda x: x[1]['mu'], reverse=True)
    top_players = sorted_players[:top_n]

    msg = "**🏅 Top des joueurs par TrueSkill :**\n"
    for rank, (key, data) in enumerate(top_players, start=1):
        if data['nb_matchs'] != 0:
            win_rate = data['nb_win'] / data['nb_matchs']
        else:
            win_rate = 0.0

        msg += (
            f"{rank}. {data['display_name']} - μ: {data['mu']:.2f} "
            f"(σ: {data['sigma']:.2f}, Win-Rate: {win_rate:.2f})\n"
        )

    await interaction.response.send_message(msg)

import itertools
import math

@tree.command(name="team", description="Génère deux équipes équilibrées à partir d'une liste de joueurs.")
@app_commands.describe(joueurs="Noms des joueurs séparés par des espaces (nombre pair requis)")
async def team(interaction: discord.Interaction, joueurs: str):
    players = load_players()
    noms = joueurs.split()
    noms = [p.lower() for p in noms]

    if len(noms) % 2 != 0:
        await interaction.response.send_message("❌ Le nombre de joueurs doit être pair.", ephemeral=True)
        return

    for name in noms:
        register_player(players, name)

    save_players(players)

    best_diff = math.inf
    best_team_a = []
    best_team_b = []

    for combo in itertools.combinations(noms, len(noms) // 2):
        team_a = list(combo)
        team_b = [p for p in noms if p not in team_a]

        mu_a = sum(players[p]["mu"] for p in team_a)
        mu_b = sum(players[p]["mu"] for p in team_b)
        diff = abs(mu_a - mu_b)

        if diff < best_diff:
            best_diff = diff
            best_team_a = team_a
            best_team_b = team_b

    def format_team(team):
        return "\n".join(
            f"- {players[p]['display_name']} ({players[p]['mu']:.2f})"
            for p in team
        )

    mu_A = sum(players[p]['mu'] for p in best_team_a) / len(best_team_a)
    mu_B = sum(players[p]['mu'] for p in best_team_b) / len(best_team_b)
    msg = "**⚖️ Équipes équilibrées :**\n\n"
    msg += f"**Équipe A** (μ = {mu_A:.2f}) :\n{format_team(best_team_a)}\n\n"
    msg += f"**Équipe B** (μ = {mu_B:.2f}) :\n{format_team(best_team_b)}\n\n"
    msg += f"Différence μ : {abs(mu_A - mu_B):.2f}"

    await interaction.response.send_message(msg)


@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")
    try:
        synced = await tree.sync()
        print(f"📦 Slash commands synchronisées : {len(synced)} commandes")
    except Exception as e:
        print(f"⚠️ Erreur de sync : {e}")

bot.run(TOKEN)