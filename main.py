import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import itertools

# Chargement config
with open("config.json", "r") as f:
    config = json.load(f)

TOKEN = config["token"]
DATA_FILE = "players.json"
ELO_INIT = 1000
K = 32

# Bot setup
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree  # Slash command handler

# Fonctions utilitaires
def load_players():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_players(players):
    with open(DATA_FILE, "w") as f:
        json.dump(players, f, indent=2)

def register_player(players, name):
    if name not in players:
        players[name] = {"elo": ELO_INIT, "nb_matchs": 0}

def expected_score(elo_a, elo_b):
    return 1 / (1 + 10 ** ((elo_b - elo_a) / 400))

def update_elo(elo, expected, result):
    return round(elo + K * (result - expected))

def process_match(players, team_a, team_b, winner):
    elo_a_avg = sum(players[p]["elo"] for p in team_a) / len(team_a)
    elo_b_avg = sum(players[p]["elo"] for p in team_b) / len(team_b)

    result_a = 1 if winner == "A" else 0
    result_b = 1 - result_a

    for p in team_a:
        exp = expected_score(players[p]["elo"], elo_b_avg)
        players[p]["elo"] = update_elo(players[p]["elo"], exp, result_a)
        players[p]["nb_matchs"] += 1

    for p in team_b:
        exp = expected_score(players[p]["elo"], elo_a_avg)
        players[p]["elo"] = update_elo(players[p]["elo"], exp, result_b)
        players[p]["nb_matchs"] += 1

def generate_balanced_teams(players, player_names):
    if len(player_names) % 2 != 0:
        return None, None, "Nombre impair de joueurs."

    team_size = len(player_names) // 2
    best = None
    min_diff = float("inf")

    for combo in itertools.combinations(player_names, team_size):
        team_a = list(combo)
        team_b = [p for p in player_names if p not in team_a]

        elo_a = sum(players[p]["elo"] for p in team_a)
        elo_b = sum(players[p]["elo"] for p in team_b)
        diff = abs(elo_a - elo_b)

        if diff < min_diff:
            min_diff = diff
            best = (team_a, team_b)

    return best[0], best[1], f"Différence ELO : {min_diff}"

# Slash commands
@tree.command(name="elo_add", description="Ajoute un ou plusieurs joueurs au classement.")
@app_commands.describe(joueurs="Noms des joueurs séparés par des espaces")
async def elo_add(interaction: discord.Interaction, joueurs: str):
    players = load_players()
    noms = joueurs.split()
    for name in noms:
        register_player(players, name)
    save_players(players)
    await interaction.response.send_message(f"✅ Joueurs enregistrés : {', '.join(noms)}", ephemeral=True)

@tree.command(name="elo_match", description="Enregistre un match entre deux équipes.")
@app_commands.describe(winner="Vainqueur (A ou B)", equipe_a="Liste des joueurs équipe A", equipe_b="Liste équipe B")
async def elo_match(interaction: discord.Interaction, winner: str, equipe_a: str, equipe_b: str):
    players = load_players()
    team_a = equipe_a.split()
    team_b = equipe_b.split()
    winner = winner.upper()

    for p in team_a + team_b:
        register_player(players, p)

    if winner not in ["A", "B"]:
        await interaction.response.send_message("❌ Le vainqueur doit être A ou B.", ephemeral=True)
        return

    process_match(players, team_a, team_b, winner)
    save_players(players)

    await interaction.response.send_message(f"🏆 Match enregistré. Victoire équipe {winner}.", ephemeral=True)

@tree.command(name="elo_teams", description="Génère automatiquement des équipes équilibrées.")
@app_commands.describe(joueurs="Noms des joueurs séparés par des espaces")
async def elo_teams(interaction: discord.Interaction, joueurs: str):
    players = load_players()
    noms = joueurs.split()
    noms = [j for j in noms if j in players]
    if len(noms) < 2:
        await interaction.response.send_message("❌ Pas assez de joueurs.", ephemeral=True)
        return

    team_a, team_b, msg = generate_balanced_teams(players, noms)
    if not team_a:
        await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
        return

    a_desc = "\n".join([f"- {p} ({players[p]['elo']})" for p in team_a])
    b_desc = "\n".join([f"- {p} ({players[p]['elo']})" for p in team_b])

    await interaction.response.send_message(
        f"📌 **Équipe A**\n{a_desc}\n\n📌 **Équipe B**\n{b_desc}\n\n{msg}"
    )

# Ready + Sync
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")
    try:
        synced = await tree.sync()
        print(f"📦 Slash commands synchronisées : {len(synced)} commandes")
    except Exception as e:
        print(f"⚠️ Erreur de sync : {e}")

bot.run(TOKEN)
