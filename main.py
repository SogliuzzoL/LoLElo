import discord
from discord.ext import commands
from discord import app_commands
from typing import List
from trueskill import Rating, rate
import json
import os
import itertools
import math
import matplotlib.pyplot as plt
import seaborn as sns
import io

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
@app_commands.describe(top_n="Nombre de joueurs à afficher")
async def top(interaction: discord.Interaction, top_n: int = 25):
    players = load_players()
    if not players:
        await interaction.response.send_message("❌ Aucun joueur enregistré.", ephemeral=True)
        return

    sorted_players = sorted(players.items(), key=lambda x: x[1].get('mu', 0), reverse=True)
    top_players = sorted_players[:top_n]

    # Données pour l'histogramme
    noms = [data.get('display_name', key) for key, data in top_players]
    mus = [data.get('mu', 0) for _, data in top_players]
    sigmas = [data.get('sigma', 0) for _, data in top_players]

    # Création du graphique avec barres d'incertitude
    plt.figure(figsize=(10, 0.4 * len(noms) + 2))
    y_pos = range(len(noms))
    plt.barh(y_pos, mus, xerr=sigmas, align='center', color='mediumseagreen', ecolor='black', capsize=5)
    plt.yticks(y_pos, noms)
    plt.xlabel("μ (Moyenne de performance)")
    plt.title("Classement TrueSkill avec incertitude (σ)")
    plt.gca().invert_yaxis()
    plt.grid(axis='x', linestyle='--', alpha=0.5)
    plt.tight_layout()

    # Sauvegarde en mémoire
    buffer = io.BytesIO()
    plt.savefig(buffer, format="png")
    buffer.seek(0)
    plt.close()

    file = discord.File(buffer, filename="top_players.png")

    # Message texte
    msg = "**🏅 Top des joueurs par TrueSkill :**\n"
    for rank, (key, data) in enumerate(top_players, start=1):
        nb_matchs = data.get('nb_matchs', 0)
        nb_win = data.get('nb_win', 0)
        win_rate = (nb_win / nb_matchs) * 100 if nb_matchs > 0 else 0.0

        msg += (
            f"{rank}. {data.get('display_name', key)} - μ: {data.get('mu', 0):.2f} "
            f"(σ: {data.get('sigma', 0):.2f}, WR: {win_rate:.2f}%, Matches: {nb_matchs})\n"
        )

    await interaction.response.send_message(content=msg, file=file)



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