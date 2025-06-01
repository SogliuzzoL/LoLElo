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

def load_players():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_players(players):
    with open(DATA_FILE, "w") as f:
        json.dump(players, f, indent=2)

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

def register_player(players, name):
    key = name.lower()
    if key not in players:
        players[key] = {"elo": ELO_INIT, "nb_matchs": 0, "display_name": name}

@tree.command(name="elo_add", description="Ajoute un ou plusieurs joueurs au classement.")
@app_commands.describe(joueurs="Noms des joueurs séparés par des espaces")
async def elo_add(interaction: discord.Interaction, joueurs: str):
    players = load_players()
    noms = joueurs.split()
    for name in noms:
        register_player(players, name)
    save_players(players)
    await interaction.response.send_message(f"✅ Joueurs enregistrés : {', '.join(noms)}", ephemeral=True)

@tree.command(name="elo_teams", description="Génère automatiquement des équipes équilibrées.")
@app_commands.describe(joueurs="Noms des joueurs séparés par des espaces")
async def elo_teams(interaction: discord.Interaction, joueurs: str):
    players = load_players()
    noms = joueurs.split()
    noms_valides = [j for j in noms if j.lower() in players]

    if len(noms_valides) < 2:
        await interaction.response.send_message("❌ Pas assez de joueurs.", ephemeral=True)
        return

    team_a, team_b, msg = generate_balanced_teams(players, [j.lower() for j in noms_valides])
    if not team_a:
        await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
        return

    # Calcul de l'elo moyen pour chaque équipe
    elo_moyen_a = sum(players[p]["elo"] for p in team_a) / len(team_a)
    elo_moyen_b = sum(players[p]["elo"] for p in team_b) / len(team_b)

    a_desc = "\n".join([f"- {players[p]['display_name']} ({players[p]['elo']})" for p in team_a])
    b_desc = "\n".join([f"- {players[p]['display_name']} ({players[p]['elo']})" for p in team_b])

    await interaction.response.send_message(
        f"📌 **Équipe A** (ELO moyen : {elo_moyen_a:.1f})\n{a_desc}\n\n"
        f"📌 **Équipe B** (ELO moyen : {elo_moyen_b:.1f})\n{b_desc}\n\n{msg}"
    )


@tree.command(name="elo_match", description="Enregistre un match entre deux équipes.")
@app_commands.describe(winner="Vainqueur (A ou B)", equipe_a="Liste des joueurs équipe A", equipe_b="Liste équipe B")
async def elo_match(interaction: discord.Interaction, winner: str, equipe_a: str, equipe_b: str):
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

    # Sauvegarde des ELO avant le match
    old_elos = {p: players[p]["elo"] for p in all_players}

    # Traitement du match
    process_match(players, team_a, team_b, winner)
    save_players(players)

    # Création du message public
    def format_change(p):
        old = old_elos[p]
        new = players[p]["elo"]
        diff = new - old
        signe = "➕" if diff >= 0 else "➖"
        return f"{p} : {old} → {new} ({signe}{abs(diff)})"

    msg = f"🏆 **Match enregistré - Victoire équipe {winner}**\n\n"
    msg += "**Équipe A :**\n" + "\n".join([format_change(p) for p in team_a]) + "\n\n"
    msg += "**Équipe B :**\n" + "\n".join([format_change(p) for p in team_b])

    await interaction.response.send_message(msg)

@tree.command(name="elo_top", description="Affiche le classement des joueurs par Elo.")
@app_commands.describe(top_n="Nombre de joueurs à afficher (par défaut 5)")
async def elo_top(interaction: discord.Interaction, top_n: int = 5):
    players = load_players()
    if not players:
        await interaction.response.send_message("❌ Aucun joueur enregistré.", ephemeral=True)
        return

    sorted_players = sorted(players.items(), key=lambda x: x[1]['elo'], reverse=True)
    top_players = sorted_players[:top_n]

    msg = "**🏅 Top des joueurs par Elo :**\n"
    for rank, (key, data) in enumerate(top_players, start=1):
        msg += f"{rank}. {data['display_name']} - Elo: {data['elo']} (Matches: {data['nb_matchs']})\n"

    await interaction.response.send_message(msg)


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
