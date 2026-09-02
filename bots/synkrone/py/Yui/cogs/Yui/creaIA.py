import asyncio
import logging
import os
import time
from collections import defaultdict, deque

import aiohttp
import discord
from discord.ext import commands
from discord import ui

log = logging.getLogger("ia_generator")

# ──────────────────────────────────────────────────────────────
# IMPORT DU CONFIG MANAGER (Cohérence Visuelle)
# ──────────────────────────────────────────────────────────────
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None
    log.warning("Config Manager introuvable, utilisation des embeds par défaut.")

# ──────────────────────────────────────────────────────────────
# CONFIGURATION GLOBALE IA & SYSTEM PROMPT
# ──────────────────────────────────────────────────────────────
GROQ_API_KEY     = ""  # Chargé dynamiquement via les variables d'environnement
GROQ_URL         = "https://api.groq.com/openai/v1/chat/completions"
MODEL            = "llama-3.3-70b-versatile"
MAX_HISTORY      = 10
MAX_TOKENS       = 2000
TYPING_DELAY     = 0.4
COOLDOWN_SECONDS = 0

SYSTEM_PROMPT = (
    "Tu es un Architecte Discord Expert et Community Manager de très haut niveau. "
    "Ton but principal est d'aider à concevoir, structurer et développer des serveurs Discord ultra-premium, esthétiques et optimisés. "
    "Tu as une connaissance absolue des permissions Discord, des catégories, des salons (textuels, vocaux, forums) et de la hiérarchie des rôles. "
    "Règles de comportement : "
    "- Adopte le ton d'un chef de projet ou d'un architecte : professionnel, créatif, précis, concis et inspirant. "
    "- Tes conseils doivent toujours proposer des structures logiques, modernes (avec des émojis élégants) et adaptées à l'expérience utilisateur (UX). "
    "- Ne donne pas d'exemples de code, concentre-toi sur le design de communautés. "
    "- Réponds en français par défaut. "
    "Déclencheurs de réponses spécifiques : "
    "- Sur ton origine/créateur : 'Je suis une IA architecte développée par 𝑽𝒆𝒙.' "
    "- Sur le support : ':link: Besoin d'aide technique ? Rejoignez [𝑺𝒚𝒏𝒌𝒓𝒐𝒏𝒆 𝑺𝒖𝒑𝒑𝒐𝒓𝒕](https://discord.gg/p768u2Pgp3)' "
    "- Sur tes capacités : 'Je peux concevoir des serveurs sur mesure de A à Z. Utilisez la commande `/newserv` pour démarrer l'assistant !'"
)

# ──────────────────────────────────────────────────────────────
# COG : INTELLIGENCE ARTIFICIELLE (CŒUR)
# ──────────────────────────────────────────────────────────────

class IACog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._histories: dict[int, deque] = defaultdict(lambda: deque(maxlen=MAX_HISTORY * 2))
        self._cooldowns: dict[int, float] = {}
        self._session: aiohttp.ClientSession | None = None

    async def cog_load(self):
        global GROQ_API_KEY
        GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
        self._session = aiohttp.ClientSession()

    async def cog_unload(self):
        if self._session:
            await self._session.close()

    async def _ask(self, user_id: int, user_message: str, custom_system_prompt: str = None, temperature: float = 0.5) -> str:
        if not GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY manquante dans les variables d'environnement.")

        history = self._histories[user_id]
        sys_prompt = custom_system_prompt if custom_system_prompt else SYSTEM_PROMPT
        
        messages = [{"role": "system", "content": sys_prompt}]
        if not custom_system_prompt:  
            messages += list(history)
            
        messages.append({"role": "user", "content": user_message})

        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": MODEL, 
            "messages": messages, 
            "max_tokens": MAX_TOKENS,
            "temperature": temperature
        }

        async with self._session.post(GROQ_URL, json=payload, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise ConnectionError(f"HTTP {resp.status} — {text[:200]}")
            data = await resp.json()

        reply = data["choices"][0]["message"]["content"].strip()
        
        if not custom_system_prompt:
            history.append({"role": "user", "content": user_message})
            history.append({"role": "assistant", "content": reply})
            
        return reply

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None: return
        if self.bot.user not in message.mentions and not (message.reference and isinstance(message.reference.resolved, discord.Message) and message.reference.resolved.author == self.bot.user):
            return

        content = message.content.replace(f"<@{self.bot.user.id}>", "").replace(f"<@!{self.bot.user.id}>", "").strip()
        if not content: return

        now = time.monotonic()
        if COOLDOWN_SECONDS - (now - self._cooldowns.get(message.author.id, 0.0)) > 0:
            return
        self._cooldowns[message.author.id] = now

        async with message.channel.typing():
            await asyncio.sleep(TYPING_DELAY)
            try:
                reply = await self._ask(message.author.id, content)
                if len(reply) <= 1900:
                    await message.reply(reply, mention_author=False)
                else:
                    import tempfile
                    with tempfile.NamedTemporaryFile('w+', delete=False, suffix='.txt', encoding='utf-8') as tmp:
                        tmp.write(reply)
                    await message.reply("Fichier texte ci-joint :", file=discord.File(tmp.name, "reponse.txt"), mention_author=False)
            except Exception as e:
                await message.reply(f"❌ Erreur : {e}", mention_author=False)

    @commands.hybrid_command(name="ia-reset", aliases=["ia_reset"])
    async def ia_reset(self, ctx: commands.Context):
        """Réinitialise ta mémoire de conversation avec l'IA."""
        self._histories[ctx.author.id].clear()
        await ctx.reply("🧠 Mémoire réinitialisée. On repart de zéro !", ephemeral=True)


# ──────────────────────────────────────────────────────────────
# MODALS (POUR LA SAISIE UTILISATEUR)
# ──────────────────────────────────────────────────────────────

class ProjectModal(ui.Modal):
    def __init__(self, view):
        super().__init__(title="Définition du projet", timeout=300)
        self.parent_view = view
        
        self.theme_input = ui.TextInput(
            label="Thème principal du serveur", 
            style=discord.TextStyle.short, 
            placeholder="Ex: Entreprise, E-sport, Communauté Gaming, RPG...", 
            required=True
        )
        self.desc_input = ui.TextInput(
            label="Description détaillée & Idées", 
            style=discord.TextStyle.paragraph, 
            placeholder="Décrivez l'esprit du serveur. Quels types de salons ou d'espaces souhaitez-vous ?", 
            required=True
        )
        self.add_item(self.theme_input)
        self.add_item(self.desc_input)

    async def on_submit(self, interaction: discord.Interaction):
        self.parent_view.answers["theme"] = self.theme_input.value
        self.parent_view.answers["description"] = self.desc_input.value
        self.parent_view.step = 1
        await self.parent_view.send_step(interaction)
        
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        log.error(f"Erreur Modal: {error}")
        msg = f"❌ Une erreur interne est survenue : {error}"
        if not interaction.response.is_done():
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            await interaction.followup.send(msg, ephemeral=True)


# ──────────────────────────────────────────────────────────────
# INTERFACE UTILISATEUR UNIQUE (MISE À JOUR DYNAMIQUE)
# ──────────────────────────────────────────────────────────────

class NewServerView(ui.View):
    def __init__(self, ctx: commands.Context, bot: commands.Bot):
        super().__init__(timeout=900)
        self.ctx = ctx
        self.bot = bot
        self.step = 0
        self.message = None # Mémorise le message d'origine pour l'éditer en continu
        self.answers = {"theme": "", "description": "", "ai_channels": "", "ai_roles": ""}

    def get_embed(self, title: str, description: str, color: int = 0x2ecc71):
        if config_manager and self.ctx.guild:
            return config_manager.get_formatted_embed(
                guild=self.ctx.guild, 
                user=self.ctx.author,
                bot=self.bot,
                title=title, 
                description=description
            )
        return discord.Embed(title=title, description=description, color=color)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ Ce menu ne vous est pas destiné.", ephemeral=True)
            return False
        return True

    async def send_step(self, interaction: discord.Interaction = None):
        """Met à jour l'interface en fonction de l'étape actuelle."""
        self.clear_items()

        # ÉTAPE 0 : LE PROJET
        if self.step == 0:
            embed = self.get_embed(
                "🛠️ Création de serveur IA — Le Projet", 
                "L'IA a besoin de connaître le thème principal et la description de votre futur serveur pour générer une architecture sur mesure."
            )
            btn = ui.Button(label="Définir le projet", style=discord.ButtonStyle.primary, emoji="📝")
            async def theme_cb(i): await i.response.send_modal(ProjectModal(self))
            btn.callback = theme_cb
            self.add_item(btn)

        # ÉTAPE 1 : CATÉGORIES & SALONS
        elif self.step == 1:
            desc = (
                f"**Thème :** {self.answers['theme']}\n"
                f"**Description :** {self.answers['description']}\n\n"
                "Appuyez sur `Générer les Salons` pour que l'IA propose les catégories et les salons.\n\n"
            )
            if self.answers["ai_channels"]:
                desc += f"**Proposition de l'IA :**\n{self.answers['ai_channels']}\n"
                
            embed = self.get_embed("📁 Étape 1 : Catégories et Salons", desc)
            
            self.add_item(GenerateChannelsButton(self))
            if self.answers["ai_channels"]:
                self.add_item(ContinueButton(self))
            self.add_item(BackButton(self))

        # ÉTAPE 2 : RÔLES
        elif self.step == 2:
            desc = "Appuyez sur `Générer les Rôles` pour que l'IA propose une hiérarchie adaptée à votre serveur.\n\n"
            if self.answers["ai_roles"]:
                desc += f"**Proposition de l'IA :**\n{self.answers['ai_roles']}\n"
                
            embed = self.get_embed("🎭 Étape 2 : Hiérarchie des Rôles", desc)
            
            self.add_item(GenerateRolesButton(self))
            if self.answers["ai_roles"]:
                self.add_item(ContinueButton(self))
            self.add_item(BackButton(self))

        # ÉTAPE 3 : CRÉATION FINALE
        elif self.step == 3:
            embed = self.get_embed(
                "⚙️ Lancement de la Forge", 
                "L'architecture (Salons et Rôles) est validée. Cliquez sur le bouton ci-dessous pour ordonner au bot de tout créer physiquement.\n\n"
                "⚠️ **Action irréversible sur le serveur actuel.**"
            )
            self.add_item(LaunchButton(self))
            self.add_item(BackButton(self))

        # Moteur d'édition du message unique
        if interaction:
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed, view=self)
            else:
                await interaction.response.edit_message(embed=embed, view=self)
        else:
            if self.message:
                await self.message.edit(embed=embed, view=self)
            else:
                self.message = await self.ctx.send(embed=embed, view=self)


class BackButton(ui.Button):
    def __init__(self, parent_view):
        super().__init__(label="Retour", style=discord.ButtonStyle.secondary, row=2)
        self.parent_view = parent_view
    async def callback(self, interaction: discord.Interaction):
        self.parent_view.step = max(0, self.parent_view.step - 1)
        await self.parent_view.send_step(interaction)

class ContinueButton(ui.Button):
    def __init__(self, parent_view):
        super().__init__(label="Valider l'étape", style=discord.ButtonStyle.success)
        self.parent_view = parent_view
    async def callback(self, interaction: discord.Interaction):
        self.parent_view.step += 1
        await self.parent_view.send_step(interaction)


# ──────────────────────────────────────────────────────────────
# BOUTONS GÉNÉRATEURS (AVEC ÉCRANS DE CHARGEMENT)
# ──────────────────────────────────────────────────────────────

class GenerateChannelsButton(ui.Button):
    def __init__(self, parent_view):
        is_retry = bool(parent_view.answers.get("ai_channels"))
        label = "Relancer l'IA (Autre proposition)" if is_retry else "Générer les Salons"
        style = discord.ButtonStyle.danger if is_retry else discord.ButtonStyle.primary
        super().__init__(label=label, style=style, emoji="📁")
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        ia_cog = self.parent_view.bot.get_cog("IACog")
        if not ia_cog:
            return await interaction.response.send_message("❌ Module IA inactif.", ephemeral=True)

        # 1. Écran de chargement (sur le même message)
        loading_embed = discord.Embed(title="⏳ Réflexion de l'IA...", description="Analyse du projet et génération de l'architecture des salons en cours...", color=0xf1c40f)
        await interaction.response.edit_message(embed=loading_embed, view=None)

        # 2. Paramétrage IA
        temp = 0.9 if self.parent_view.answers.get("ai_channels") else 0.4
        creativity = "Fais une proposition totalement différente et très originale. " if temp > 0.5 else ""

        sys_prompt = (
            "Tu es un générateur de serveur Discord ultra-premium. "
            "Tu dois générer UNIQUEMENT les catégories et salons demandés. "
            "Format OBLIGATOIRE et STRICT (pas de texte avant ni après) :\n\n"
            "CATÉGORIE: 📂・Nom de la Catégorie\n"
            "- 💬・nom-du-salon\n"
            "- 🔊・autre-salon-vocal\n"
            "(Répète cette structure pour toutes les catégories nécessaires)\n\n"
            "IMPORTANT: Les CATÉGORIES ET les SALONS DOIVENT obligatoirement inclure un emoji approprié, suivi du séparateur '・'."
        )

        prompt = f"{creativity}Génère l'architecture des Catégories et Salons pour un serveur ayant pour thème '{self.parent_view.answers['theme']}'. Voici sa description : {self.parent_view.answers['description']}"
        
        # 3. Requête et mise à jour
        try:
            response = await ia_cog._ask(interaction.user.id, prompt, custom_system_prompt=sys_prompt, temperature=temp)
            self.parent_view.answers["ai_channels"] = response
            await self.parent_view.send_step(interaction)
        except Exception as e:
            err_embed = discord.Embed(title="❌ Erreur IA", description=str(e), color=0xe74c3c)
            await interaction.edit_original_response(embed=err_embed, view=self.parent_view)

class GenerateRolesButton(ui.Button):
    def __init__(self, parent_view):
        is_retry = bool(parent_view.answers.get("ai_roles"))
        label = "Relancer l'IA (Autre proposition)" if is_retry else "Générer les Rôles"
        style = discord.ButtonStyle.danger if is_retry else discord.ButtonStyle.primary
        super().__init__(label=label, style=style, emoji="🎭")
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        ia_cog = self.parent_view.bot.get_cog("IACog")
        if not ia_cog:
            return await interaction.response.send_message("❌ Module IA inactif.", ephemeral=True)

        # Écran de chargement
        loading_embed = discord.Embed(title="⏳ Réflexion de l'IA...", description="Création de la hiérarchie des rôles en cours...", color=0xf1c40f)
        await interaction.response.edit_message(embed=loading_embed, view=None)

        temp = 0.9 if self.parent_view.answers.get("ai_roles") else 0.4
        creativity = "Fais une proposition de rôles différente et originale. " if temp > 0.5 else ""

        sys_prompt = (
            "Tu es un générateur de serveur Discord ultra-premium. "
            "Tu dois générer UNIQUEMENT les rôles demandés. "
            "Format OBLIGATOIRE et STRICT (pas de texte avant ni après) :\n\n"
            "RÔLE: 👑・Fondateur\n"
            "RÔLE: 🛡️・Modérateur\n"
            "(Répète cette structure pour tous les rôles nécessaires)\n\n"
            "IMPORTANT: Les RÔLES DOIVENT obligatoirement inclure un emoji approprié, suivi du séparateur '・'."
        )

        prompt = f"{creativity}Génère une hiérarchie complète de rôles pour un serveur ayant pour thème '{self.parent_view.answers['theme']}'. Description du projet : {self.parent_view.answers['description']}"
        
        try:
            response = await ia_cog._ask(interaction.user.id, prompt, custom_system_prompt=sys_prompt, temperature=temp)
            self.parent_view.answers["ai_roles"] = response
            await self.parent_view.send_step(interaction)
        except Exception as e:
            err_embed = discord.Embed(title="❌ Erreur IA", description=str(e), color=0xe74c3c)
            await interaction.edit_original_response(embed=err_embed, view=self.parent_view)


# ──────────────────────────────────────────────────────────────
# BOUTON CRÉATION PHYSIQUE (SUR LE MÊME MESSAGE)
# ──────────────────────────────────────────────────────────────

class LaunchButton(ui.Button):
    def __init__(self, parent_view):
        super().__init__(label="🚀 Lancer la Forge", style=discord.ButtonStyle.danger)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        # 1. On remplace le message par un écran de travail
        work_embed = discord.Embed(
            title="🔨 Forge en cours...", 
            description="Le bot crée actuellement l'architecture sur votre serveur.\n\nVeuillez patienter quelques instants et **ne supprimez pas ce message**.", 
            color=0xe67e22
        )
        await interaction.response.edit_message(embed=work_embed, view=None)
        
        guild = interaction.guild
        channels_structure = self.parent_view.answers["ai_channels"]
        roles_structure = self.parent_view.answers["ai_roles"]
        current_category = None
        
        try:
            # Création Salons & Catégories
            for line in channels_structure.split('\n'):
                line = line.strip()
                if not line: continue
                
                if line.upper().startswith("CATÉGORIE:") or line.upper().startswith("CATEGORIE:"):
                    cat_name = line.split(":", 1)[1].strip()
                    current_category = await guild.create_category(name=cat_name[:100])
                    await asyncio.sleep(0.5) 
                
                elif line.startswith("-") or line.startswith("•"):
                    chan_name = line[1:].strip()
                    if current_category:
                        await guild.create_text_channel(name=chan_name[:100], category=current_category)
                    else:
                        await guild.create_text_channel(name=chan_name[:100])
                    await asyncio.sleep(0.5) 

            # Création Rôles
            for line in roles_structure.split('\n'):
                line = line.strip()
                if not line: continue
                
                if line.upper().startswith("RÔLE:") or line.upper().startswith("ROLE:"):
                    role_name = line.split(":", 1)[1].strip()
                    # Les rôles sont créés sans permission admin par défaut pour la sécurité
                    await guild.create_role(name=role_name[:100], mentionable=True, reason="Création IA - NewServ")
                    await asyncio.sleep(0.5)
            
            # 2. On met à jour le message pour dire que c'est fini !
            success_embed = discord.Embed(
                title="✅ Forge Terminée", 
                description="L'architecture a été déployée avec succès sur le serveur !", 
                color=0x2ecc71
            )
            await interaction.edit_original_response(embed=success_embed)
            
        except discord.Forbidden:
            err_embed = discord.Embed(title="❌ Erreur de Permissions", description="Le bot n'a pas les droits 'Gérer les salons' ou 'Gérer les rôles'.", color=0xe74c3c)
            await interaction.edit_original_response(embed=err_embed)
        except Exception as e:
            err_embed = discord.Embed(title="❌ Erreur Inattendue", description=f"```py\n{e}\n```", color=0xe74c3c)
            await interaction.edit_original_response(embed=err_embed)


# ──────────────────────────────────────────────────────────────
# COG : SETUP ET COMMANDE DE LANCEMENT
# ──────────────────────────────────────────────────────────────

class ServerBuilderCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="newserv", description="Crée un serveur Discord premium de A à Z via l'IA.")
    @commands.has_permissions(administrator=True)
    async def newserv(self, ctx: commands.Context):
        view = NewServerView(ctx, self.bot)
        # Enregistre le premier message pour pouvoir l'éditer plus tard
        view.message = await ctx.send(embed=view.get_embed("Chargement...", "Veuillez patienter"), view=view)
        await view.send_step()

    @newserv.error
    async def newserv_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            error_msg = "❌ Vous devez posséder la permission **Administrateur** pour utiliser cette commande."
            if ctx.interaction:
                await ctx.interaction.response.send_message(error_msg, ephemeral=True)
            else:
                await ctx.send(error_msg)
        else:
            await ctx.send(f"❌ Une erreur inattendue est survenue : {error}")

async def setup(bot: commands.Bot):
    await bot.add_cog(IACog(bot))
    await bot.add_cog(ServerBuilderCog(bot))