import io
import itertools
import json
import math
import os
import time
from typing import List

import discord
import matplotlib.cm as cm
import matplotlib.pyplot as plt
import numpy as np
from discord import app_commands
from discord.ext import commands
from trueskill import Rating, rate

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
        players[key] = {
            "mu": MU,
            "sigma": SIGMA,
            "nb_matchs": 0,
            "nb_win": 0,
            "display_name": name,
            "last_match": 0
        }

def process_match(players, team_a, team_b, winner):
    team_A = [Rating(mu=players[player]["mu"], sigma=players[player]["sigma"]) for player in team_a]
    team_B = [Rating(mu=players[player]["mu"], sigma=players[player]["sigma"]) for player in team_b]
    ranks = [0, 1] if winner == "A" else [1, 0]

    team_A, team_B = rate([team_A, team_B], ranks=ranks)
    now = int(time.time())

    for (player, rating) in zip(team_a, team_A):
        players[player]["mu"] = rating.mu
        players[player]["sigma"] = rating.sigma
        players[player]["nb_matchs"] += 1
        players[player]["last_match"] = now
        if winner == "A":
            players[player]["nb_win"] += 1

    for (player, rating) in zip(team_b, team_B):
        players[player]["mu"] = rating.mu
        players[player]["sigma"] = rating.sigma
        players[player]["nb_matchs"] += 1
        players[player]["last_match"] = now
        if winner == "B":
            players[player]["nb_win"] += 1


def compute_ranks(mus):
    percentiles = np.percentile(mus, [0, 15, 35, 60, 80, 95])
    def get_rank(mu):
        if mu < percentiles[1]:
            return "🥉 Bronze"
        elif mu < percentiles[2]:
            return "🥈 Silver"
        elif mu < percentiles[3]:
            return "🥇 Gold"
        elif mu < percentiles[4]:
            return "💠 Platinum"
        elif mu < percentiles[5]:
            return "🔷 Diamond"
        else:
            return "👑 Master"
    return get_rank


# Bot setup
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree


# ---------------------------------------------------
# Vue interactive pour le classement TrueSkill
# ---------------------------------------------------

class TopView(discord.ui.View):
    def __init__(self, bot, top_n=25, offset=0, show_all=False):
        super().__init__(timeout=120)
        self.bot = bot
        self.top_n = top_n
        self.offset = offset
        self.show_all = show_all

    async def update_message(self, interaction: discord.Interaction):
        players = load_players()
        if not players:
            await interaction.response.edit_message(content="❌ Aucun joueur enregistré.", attachments=[], view=self)
            return

        two_weeks_ago = int(time.time()) - 14 * 24 * 60 * 60

        if self.show_all:
            recent_players = players
        else:
            recent_players = {
                key: data for key, data in players.items()
                if data.get("last_match", 0) >= two_weeks_ago
            }

        if not recent_players:
            await interaction.response.edit_message(content="❌ Aucun joueur actif dans les 2 dernières semaines.", attachments=[], view=self)
            return

        sorted_players = sorted(recent_players.items(), key=lambda x: x[1].get('mu', 0), reverse=True)
        top_players = sorted_players[self.offset:self.offset + self.top_n]

        if not top_players:
            await interaction.response.edit_message(content="❌ Aucun joueur trouvé dans cette tranche.", attachments=[], view=self)
            return

        noms = [data.get('display_name', key) for key, data in top_players]
        mus = [data.get('mu', 0) for _, data in top_players]
        sigmas = [data.get('sigma', 0) for _, data in top_players]

        mus_recent = [players[player]['mu'] for player in recent_players if player in players]
        get_rank = compute_ranks(mus_recent)

        norm = plt.Normalize(min(mus), max(mus))
        colors = cm.viridis(norm(mus))

        plt.figure(figsize=(10, 0.4 * len(noms) + 2))
        y_pos = range(len(noms))
        plt.barh(y_pos, mus, xerr=sigmas, align='center', color=colors, ecolor='black', capsize=5)
        plt.yticks(y_pos, noms)
        plt.xlabel("μ (Moyenne de performance)")
        plt.title("Classement TrueSkill avec incertitude (σ)")
        plt.gca().invert_yaxis()
        plt.grid(axis='x', linestyle='--', alpha=0.5)
        plt.tight_layout()

        buffer = io.BytesIO()
        plt.savefig(buffer, format="png")
        buffer.seek(0)
        plt.close()

        file = discord.File(buffer, filename="top_players.png")

        ranked_groups = {}
        for key, data in top_players:
            mu = data.get('mu', 0)
            rank_label = get_rank(mu)
            ranked_groups.setdefault(rank_label, []).append((key, data))

        rank_order = ["👑 Master", "🔷 Diamond", "💠 Platinum", "🥇 Gold", "🥈 Silver", "🥉 Bronze"]

        msg = f"**🏅 Classement des joueurs (de {self.offset + 1} à {self.offset + len(top_players)}) :**\n\n"
        classement = self.offset + 1
        for rank_name in rank_order:
            joueurs = ranked_groups.get(rank_name, [])
            if not joueurs:
                continue
            msg += f"__{rank_name}__\n"
            joueurs.sort(key=lambda x: x[1].get('mu', 0), reverse=True)
            for key, data in joueurs:
                nb_matchs = data.get('nb_matchs', 0)
                nb_win = data.get('nb_win', 0)
                win_rate = (nb_win / nb_matchs) * 100 if nb_matchs > 0 else 0.0
                mu = data.get('mu', 0)
                sigma = data.get('sigma', 0)
                msg += (
                    f"{classement}. {data.get('display_name', key)} • μ: {mu:.2f}, "
                    f"σ: {sigma:.2f}, WR: {win_rate:.1f}%, Matchs: {nb_matchs}\n"
                )
                classement += 1
            msg += "\n"

        await interaction.response.edit_message(content=msg, attachments=[file], view=self)

    @discord.ui.button(label="⬅️ Précédent", style=discord.ButtonStyle.primary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.offset - self.top_n >= 0:
            self.offset -= self.top_n
            await self.update_message(interaction)
        else:
            await interaction.response.send_message("🚫 Déjà au début du classement.", ephemeral=True)

    @discord.ui.button(label="➡️ Suivant", style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        players = load_players()
        total = len(players)
        if self.offset + self.top_n < total:
            self.offset += self.top_n
            await self.update_message(interaction)
        else:
            await interaction.response.send_message("🚫 Fin du classement atteinte.", ephemeral=True)

    @discord.ui.button(label="🧍 Actifs/Tous", style=discord.ButtonStyle.secondary)
    async def toggle_show_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.show_all = not self.show_all
        await self.update_message(interaction)


# ---------------------------------------------------
# Commandes du bot
# ---------------------------------------------------

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
@app_commands.describe(winner="Vainqueur (A ou B)", equipe_a="Liste des joueurs équipe A", equipe_b="Liste des joueurs équipe B")
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

    old_mu = {p: players[p]["mu"] for p in all_players}
    process_match(players, team_a, team_b, winner)
    save_players(players)

    def format_change(p):
        old = old_mu[p]
        new = players[p]["mu"]
        diff = new - old
        signe = "➕" if diff >= 0 else "➖"
        return f"{players[p]['display_name']} : {old:.2f} → {new:.2f} ({signe}{abs(diff):.2f})"

    msg = f"🏆 **Match enregistré - Victoire équipe {winner}**\n\n"
    msg += "**Équipe A :**\n" + "\n".join([format_change(p) for p in team_a]) + "\n\n"
    msg += "**Équipe B :**\n" + "\n".join([format_change(p) for p in team_b])

    await interaction.response.send_message(msg)


@tree.command(name="team", description="Génère deux équipes équilibrées à partir d'une liste de joueurs.")
@app_commands.describe(joueurs="Noms des joueurs séparés par des espaces (nombre pair requis)", sigma="Prendre en compte le sigma dans l'équilibrage")
async def team(interaction: discord.Interaction, joueurs: str, sigma: bool = True):
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

        if sigma:
            score_a = sum(players[p]["mu"] - 3 * players[p]["sigma"] for p in team_a)
            score_b = sum(players[p]["mu"] - 3 * players[p]["sigma"] for p in team_b)
        else:
            score_a = sum(players[p]["mu"] for p in team_a)
            score_b = sum(players[p]["mu"] for p in team_b)

        diff = abs(score_a - score_b)
        if diff < best_diff:
            best_diff = diff
            best_team_a = team_a
            best_team_b = team_b

    def format_team(team):
        return "\n".join(
            f"- {players[p]['display_name']} (μ : {players[p]['mu']:.2f}, μ-3σ : {(players[p]['mu'] - 3*players[p]['sigma']):.2f})"
            for p in team
        )

    mu_A = sum(players[p]['mu'] for p in best_team_a) / len(best_team_a)
    mu_B = sum(players[p]['mu'] for p in best_team_b) / len(best_team_b)
    score_A = sum(players[p]['mu'] - 3 * players[p]['sigma'] for p in best_team_a) / len(best_team_a)
    score_B = sum(players[p]['mu'] - 3 * players[p]['sigma'] for p in best_team_b) / len(best_team_b)

    sigma_info = 'σ pris en compte ' if sigma else ''
    msg = f"**⚖️ Équipes équilibrées {sigma_info}:**\n\n"
    msg += f"**Équipe A** (μ = {mu_A:.2f}, μ-3σ = {score_A:.2f}) :\n{format_team(best_team_a)}\n\n"
    msg += f"**Équipe B** (μ = {mu_B:.2f}, μ-3σ = {score_B:.2f}) :\n{format_team(best_team_b)}\n\n"
    msg += f"Différence • μ : {abs(mu_A - mu_B):.2f}, μ-3σ : {abs(score_A - score_B):.2f}"

    await interaction.response.send_message(msg)


@tree.command(name="top", description="Affiche le classement TrueSkill avec boutons interactifs.")
async def top(interaction: discord.Interaction, top_n: int = 25):
    view = TopView(bot, top_n=top_n)
    await interaction.response.send_message("Chargement du classement...", view=view)
    await view.update_message(interaction)


# ---------------------------------------------------
# Événements
# ---------------------------------------------------

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user}")
    try:
        synced = await tree.sync()
        print(f"📦 {len(synced)} commandes synchronisées")
    except Exception as e:
        print(f"⚠️ Erreur de sync : {e}")

bot.run(TOKEN)
