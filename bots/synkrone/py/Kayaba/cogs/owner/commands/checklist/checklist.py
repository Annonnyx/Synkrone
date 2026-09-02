import discord
from discord.ext import commands
import json
from pathlib import Path

# Liste fixe de tes fichiers
FILES_LIST = [
    "boutique.py", "collect.py", "collection.py", "daily.py", 
    "echange.py", "guide.py", "help.py", "leader.py", 
    "lvl.py", "mp.py", "premium.py", "profil.py", 
    "pvp.py", "sell.py", "shop.py", "sleep.py", 
    "stage.py", "tracker.py"
]

# Mapping des statuts avec emojis et couleurs
STATUS_MAP = {
    "Validé": {"emoji": "✅", "color": 0x2ecc71},
    "Ne fonctionne pas": {"emoji": "❌", "color": 0xe74c3c},
    "Améliorer visuel": {"emoji": "🎨", "color": 0x9b59b6},
    "Améliorer mécanique": {"emoji": "⚙️", "color": 0x3498db},
    "Non existant": {"emoji": "👻", "color": 0x95a5a6},
    "Non défini": {"emoji": "❓", "color": 0x2c2f33}
}

class CommentModal(discord.ui.Modal, title='Notes sur le fichier'):
    def __init__(self, cog, filename, view_to_refresh):
        super().__init__()
        self.cog = cog
        self.filename = filename
        self.view_to_refresh = view_to_refresh

        # Récupération des données existantes
        current_data = self.cog.check_data.get(filename, {})
        
        self.visuel = discord.ui.TextInput(
            label='Partie Visuel (UI/Embeds)',
            style=discord.TextStyle.paragraph,
            placeholder='Rien à signaler...',
            default=current_data.get("visuel", ""),
            required=False
        )
        self.technique = discord.ui.TextInput(
            label='Partie Technique (Code/Logique)',
            style=discord.TextStyle.paragraph,
            placeholder='Bugs, optimisations...',
            default=current_data.get("technique", ""),
            required=False
        )
        self.add_item(self.visuel)
        self.add_item(self.technique)

    async def on_submit(self, interaction: discord.Interaction):
        if self.filename not in self.cog.check_data:
            self.cog.check_data[self.filename] = {"status": "Non défini"}
        
        self.cog.check_data[self.filename]["visuel"] = self.visuel.value
        self.cog.check_data[self.filename]["technique"] = self.technique.value
        self.cog.save_checks()

        await interaction.response.edit_message(
            embed=self.view_to_refresh.generate_detail_embed(self.filename), 
            view=self.view_to_refresh
        )

class StatusSelect(discord.ui.Select):
    def __init__(self, cog, filename, parent_view):
        self.cog = cog
        self.filename = filename
        self.parent_view = parent_view
        
        options = [
            discord.SelectOption(label=k, emoji=v["emoji"]) 
            for k, v in STATUS_MAP.items() if k != "Non défini"
        ]
        super().__init__(placeholder="Changer l'état...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.filename not in self.cog.check_data:
            self.cog.check_data[self.filename] = {}
        
        self.cog.check_data[self.filename]["status"] = self.values[0]
        self.cog.save_checks()
        
        await interaction.response.edit_message(
            embed=self.parent_view.generate_detail_embed(self.filename), 
            view=self.parent_view
        )

class DetailView(discord.ui.View):
    def __init__(self, cog, filename):
        super().__init__(timeout=300)
        self.cog = cog
        self.filename = filename
        self.add_item(StatusSelect(cog, filename, self))

    def generate_detail_embed(self, filename):
        data = self.cog.check_data.get(filename, {"status": "Non défini"})
        status = data.get("status", "Non défini")
        config = STATUS_MAP.get(status, STATUS_MAP["Non défini"])
        
        embed = discord.Embed(title=f"📁 Dossier : {filename}", color=config["color"])
        embed.add_field(name="État actuel", value=f"{config['emoji']} **{status}**", inline=False)
        
        visuel_txt = data.get("visuel") or "*Aucune note*"
        tech_txt = data.get("technique") or "*Aucune note*"
        
        embed.add_field(name="🎨 Visuel", value=f"```\n{visuel_txt}```", inline=True)
        embed.add_field(name="⚙️ Technique", value=f"```\n{tech_txt}```", inline=True)
        
        return embed

    @discord.ui.button(label="Modifier Notes", style=discord.ButtonStyle.primary, emoji="📝", row=2)
    async def btn_comment(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CommentModal(self.cog, self.filename, self))

    @discord.ui.button(label="Retour au Sommaire", style=discord.ButtonStyle.danger, emoji="◀️", row=2)
    async def btn_retour(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=self.cog.generate_summary_embed(), 
            view=MainView(self.cog)
        )

class MainFileSelect(discord.ui.Select):
    def __init__(self, cog):
        self.cog = cog
        options = []
        for file in FILES_LIST:
            status = self.cog.check_data.get(file, {}).get("status", "Non défini")
            options.append(discord.SelectOption(
                label=file, 
                emoji=STATUS_MAP.get(status, STATUS_MAP["Non défini"])["emoji"]
            ))
        super().__init__(placeholder="Sélectionner un fichier pour voir le détail...", options=options)

    async def callback(self, interaction: discord.Interaction):
        view = DetailView(self.cog, self.values[0])
        await interaction.response.edit_message(embed=view.generate_detail_embed(self.values[0]), view=view)

class MainView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=300)
        self.add_item(MainFileSelect(cog))

class Check(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_file = Path(__file__).parent / "data" / "command_checks.json"
        self.check_data = self.load_checks()
    
    def load_checks(self):
        if self.check_file.exists():
            with open(self.check_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def save_checks(self):
        self.check_file.parent.mkdir(exist_ok=True)
        with open(self.check_file, 'w', encoding='utf-8') as f:
            json.dump(self.check_data, f, indent=4, ensure_ascii=False)

    def generate_summary_embed(self):
        embed = discord.Embed(title="🔍 Sommaire du Projet", color=0x5865F2)
        
        summary = ""
        for i, file in enumerate(FILES_LIST, 1):
            status = self.check_data.get(file, {}).get("status", "Non défini")
            emoji = STATUS_MAP.get(status, STATUS_MAP["Non défini"])["emoji"]
            # Petit indicateur si des commentaires existent
            note = " 📝" if self.check_data.get(file, {}).get("visuel") or self.check_data.get(file, {}).get("technique") else ""
            summary += f"`{i:02d}.` {emoji} **{file}**{note}\n"
        
        embed.description = summary
        return embed

    @commands.command(name="checklist")
    @commands.has_permissions(administrator=True)
    async def check(self, ctx):
        await ctx.send(embed=self.generate_summary_embed(), view=MainView(self))

async def setup(bot):
    await bot.add_cog(Check(bot))