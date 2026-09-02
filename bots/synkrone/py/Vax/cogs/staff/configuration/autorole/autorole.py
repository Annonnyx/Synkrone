# -*- coding: utf-8 -*-
"""
Module : autorole.py
Description : Système Premium de gestion des Rôles Automatiques (Base, Ancienneté étendue, Tag de Clan et Soutien).
Version : 3.5.0 - WIP Clan Tag & Infrastructure Auto-Générée
"""

import discord
from discord.ext import commands, tasks
from discord import ui
from datetime import datetime, timezone
from pathlib import Path
import json
import re
import unicodedata
import logging

logger = logging.getLogger("bot.autorole")

try:
    from cogs.addons.embed_type.utils import config_manager
    HAS_MANAGER = True
except ImportError:
    config_manager = None
    HAS_MANAGER = False

# ==============================================================================
# ----------------------------- COG AUTOROLE ----------------------------------
# ==============================================================================
class AutoRole(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.base_dir = Path(__file__).parent
        self.data_path = self.base_dir / "data" / "autorole"
        self.data_path.mkdir(parents=True, exist_ok=True)

        # Configuration exhaustive de tous les paliers demandés
        self.features_def = {
            "bot": {"label": "🤖 Bots", "cat": "base", "color": 0x7289da, "admin": True, "default_name": "🤖 Bots"},
            "membre": {"label": "👤 Membres", "cat": "base", "color": 0x95a5a6, "admin": False, "default_name": "👤 Membres"},
            
            "1_mois": {"label": "⏳ 1 Mois", "cat": "time", "color": 0x3498db, "days": 30, "default_name": "⏳ Ancien : 1 Mois"},
            "3_mois": {"label": "⏳ 3 Mois", "cat": "time", "color": 0x2ecc71, "days": 90, "default_name": "⏳ Ancien : 3 Mois"},
            "9_mois": {"label": "⏳ 9 Mois", "cat": "time", "color": 0x9b59b6, "days": 270, "default_name": "⏳ Ancien : 9 Mois"},
            "1_an": {"label": "📆 1 An", "cat": "time", "color": 0xf1c40f, "days": 365, "default_name": "📆 Vétéran : 1 An"},
            "2_ans": {"label": "📆 2 Ans", "cat": "time", "color": 0xe67e22, "days": 730, "default_name": "📆 Vétéran : 2 Ans"},
            "3_ans": {"label": "📆 3 Ans", "cat": "time", "color": 0xe74c3c, "days": 1095, "default_name": "📆 Légende : 3 Ans"},
            "5_ans": {"label": "👑 5 Ans et +", "cat": "time", "color": 0xad1457, "days": 1825, "default_name": "👑 Immortel : 5 Ans +"},
            
            "guild_tag": {"label": "🛡️ Tag de Guilde/Clan [WIP]", "cat": "tag", "color": 0x1abc9c, "default_name": "🛡️ Membre du Clan"},
            "discord_url": {"label": "🔗 Soutien Discord", "cat": "presence", "color": 0x5865F2, "default_name": "🔗 Supporteur Discord"},
            "site_url": {"label": "🌐 Soutien Web", "cat": "presence", "color": 0x2ecc71, "default_name": "🌐 Supporteur Web"}
        }
        
        self.server_data = {}
        self.check_all_roles.start()

    def cog_unload(self):
        self.check_all_roles.cancel()

    def get_or_load_data(self, guild_id: str) -> dict:
        """Charge ou initialise la configuration d'un serveur."""
        if guild_id not in self.server_data:
            path = self.data_path / f"{guild_id}.json"
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        self.server_data[guild_id] = json.load(f)
                except Exception as e:
                    logger.error(f"Erreur lecture JSON {guild_id}: {e}")
                    self.server_data[guild_id] = {"enabled_features": [], "roles": {}, "settings": {}}
            else:
                self.server_data[guild_id] = {"enabled_features": [], "roles": {}, "settings": {}}
            
            if "settings" not in self.server_data[guild_id]:
                self.server_data[guild_id]["settings"] = {"discord_url": "", "site_url": "", "forced_tag": ""}
            if "roles" not in self.server_data[guild_id]:
                self.server_data[guild_id]["roles"] = {}
                
        return self.server_data[guild_id]

    def save_data(self, guild_id: str):
        """Sauvegarde les configurations en fichier local JSON."""
        path = self.data_path / f"{guild_id}.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.server_data[guild_id], f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erreur écriture JSON {guild_id}: {e}")

    def normalize_text(self, text: str) -> str:
        """Nettoie et convertit les caractères stylisés Unicode en ASCII plat."""
        if not text:
            return ""
        return unicodedata.normalize('NFKC', text).lower().strip()

    def resolve_expected_tag(self, guild: discord.Guild, data: dict) -> str:
        """Identifie le Tag cible du serveur (Forçage > API Clan > Nom du serveur)."""
        settings = data.get("settings", {})
        if settings.get("forced_tag"):
            return self.normalize_text(settings["forced_tag"])

        # API Native Clan (Discord 2024+) - Flagged as [Work In Progress]
        if hasattr(guild, 'clan') and guild.clan and getattr(guild.clan, 'tag', None):
            return self.normalize_text(guild.clan.tag)

        # Fallback par Regex sur le nom de la guilde
        match = re.search(r'[\[\(\{](.*?)[\]\)\}]|^(\w+)\s*[\|\]\-]', guild.name)
        if match:
            return self.normalize_text(match.group(1) or match.group(2))

        return self.normalize_text(guild.name[:4])

    def check_member_tag(self, member: discord.Member, target_tag: str) -> bool:
        """Option alternative robuste : Recherche multi-critères du tag textuel."""
        if not target_tag:
            return False

        # [WIP] Vérification via l'API Native de Clan Discord
        if hasattr(member, 'clan') and member.clan and getattr(member.clan, 'tag', None):
            if self.normalize_text(member.clan.tag) == target_tag:
                return True

        # OPTION ALTERNATIVE : Analyse textuelle par tolérance de structures (ex: [Synk], Synk |, (synk))
        display_name = self.normalize_text(member.display_name)
        username = self.normalize_text(member.name)
        
        # Capture le tag isolé ou entouré de séparateurs courants
        patterns = [
            rf"\b{re.escape(target_tag)}\b",
            rf"\[{re.escape(target_tag)}\]",
            rf"\({re.escape(target_tag)}\)",
            rf"\{{{re.escape(target_tag)}\}}",
            rf"^{re.escape(target_tag)}\s*[\|⏳•\-]",
        ]
        
        for pattern in patterns:
            if re.search(pattern, display_name) or re.search(pattern, username):
                return True
                
        # Fallback ultime : simple inclusion si aucune structure n'est détectée
        return target_tag in display_name or target_tag in username

    def check_support_status(self, member: discord.Member, keyword: str) -> bool:
        """Scrutateur d'activité de statut personnalisé (Custom Status)."""
        if not keyword:
            return False
        kw = keyword.lower().strip()

        for activity in member.activities:
            if isinstance(activity, discord.CustomActivity):
                state = self.normalize_text(getattr(activity, 'state', ''))
                name = self.normalize_text(getattr(activity, 'name', ''))
                if kw in state or kw in name:
                    return True
        return False

    async def ensure_role_exists(self, guild: discord.Guild, f_key: str) -> discord.Role:
        """OPTION COMPORTEMENTALE : Crée le rôle s'il est manquant et l'enregistre."""
        gid = str(guild.id)
        data = self.get_or_load_data(gid)
        current_id = data["roles"].get(f_key)
        
        role = guild.get_role(int(current_id)) if current_id and current_id.isdigit() else None
        
        if not role:
            f_info = self.features_def[f_key]
            perms = discord.Permissions(administrator=True) if f_info.get("admin") else discord.Permissions.none()
            
            role_name = f_info["default_name"]
            if f_key == "guild_tag" and data["settings"].get("forced_tag"):
                role_name = f"🛡️ Clan [{data['settings']['forced_tag'].upper()}]"

            try:
                role = await guild.create_role(
                    name=role_name,
                    color=discord.Color(f_info["color"]),
                    hoist=True,
                    permissions=perms,
                    reason="AutoRole Premium : Initialisation de l'infrastructure"
                )
                data["roles"][f_key] = str(role.id)
                self.save_data(gid)
            except discord.Forbidden:
                logger.error(f"Permissions insuffisantes pour créer le rôle {f_key} sur {guild.name}")
                return None
        return role

    async def apply_roles_to_all(self, guild: discord.Guild):
        """Met à jour l'intégralité de la guilde."""
        data = self.get_or_load_data(str(guild.id))
        target_tag = self.resolve_expected_tag(guild, data)

        # S'assure en amont que tous les rôles activés possèdent une entité physique sur Discord
        for f_key in data.get("enabled_features", []):
            await self.ensure_role_exists(guild, f_key)

        for member in guild.members:
            await self.process_member_roles(member, data, target_tag)

    async def process_member_roles(self, member: discord.Member, data: dict, target_tag: str):
        """Attribue ou révoque les rôles d'un membre selon ses critères d'éligibilité."""
        added_roles, removed_roles = set(), set()
        now = datetime.now(timezone.utc)
        feats = data.get("enabled_features", [])
        settings = data.get("settings", {})

        for f_key, f_info in self.features_def.items():
            r_id = data["roles"].get(f_key)
            role = member.guild.get_role(int(r_id)) if r_id and r_id.isdigit() else None
            
            # S'il n'y a pas de rôle physique sur le serveur, on évite le blocage
            if not role:
                continue

            should_have_role = False

            if f_key in feats:
                if f_info["cat"] == "base":
                    if (f_key == "bot" and member.bot) or (f_key == "membre" and not member.bot):
                        should_have_role = True
                elif f_info["cat"] == "time" and not member.bot:
                    days = (now - member.joined_at).days if member.joined_at else 0
                    if days >= f_info["days"]:
                        should_have_role = True
                elif f_info["cat"] == "tag" and not member.bot:
                    if self.check_member_tag(member, target_tag):
                        should_have_role = True
                elif f_info["cat"] == "presence" and not member.bot:
                    kw = settings.get(f_key, "")
                    if kw and self.check_support_status(member, kw):
                        should_have_role = True

            if should_have_role and role not in member.roles:
                added_roles.add(role)
            elif not should_have_role and role in member.roles:
                removed_roles.add(role)

        try:
            bot_member = member.guild.get_member(self.bot.user.id)
            if bot_member:
                top_pos = bot_member.top_role.position
                clean_add = [r for r in added_roles if r.position < top_pos]
                clean_remove = [r for r in removed_roles if r.position < top_pos]

                if clean_add:
                    await member.add_roles(*clean_add, reason="AutoRole Premium : Conditions validées")
                if clean_remove:
                    await member.remove_roles(*clean_remove, reason="AutoRole Premium : Conditions expirées")
        except discord.Forbidden:
            pass

    @tasks.loop(minutes=15)
    async def check_all_roles(self):
        """Vérification cyclique asynchrone d'arrière-plan."""
        for guild in self.bot.guilds:
            try:
                if not guild.chunked:
                    await guild.chunk()
                data = self.get_or_load_data(str(guild.id))
                target_tag = self.resolve_expected_tag(guild, data)
                for member in guild.members:
                    await self.process_member_roles(member, data, target_tag)
            except Exception as e:
                logger.error(f"Erreur boucle AutoRole sur la guilde {guild.id}: {e}")

    @check_all_roles.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    @commands.hybrid_command(name="autorole", description="Ouvre l'interface de gestion de l'attribution automatique des rôles")
    @commands.has_permissions(administrator=True)
    async def autorole(self, ctx: commands.Context):
        await ctx.defer()
        if ctx.guild and not ctx.guild.chunked:
            await ctx.guild.chunk()
            
        self.get_or_load_data(str(ctx.guild.id))
        embed = await self.create_embed(ctx.guild, ctx.author)
        view = DashboardView(self, ctx.guild)
        await ctx.send(embed=embed, view=view)

    async def calculate_eligible_counts(self, guild: discord.Guild, data: dict) -> dict:
        """Compte les utilisateurs éligibles par fonctionnalité (O(N))."""
        counts = {k: 0 for k in self.features_def}
        now = datetime.now(timezone.utc)
        settings = data.get("settings", {})
        target_tag = self.resolve_expected_tag(guild, data)

        for member in guild.members:
            if member.bot:
                counts["bot"] += 1
            else:
                counts["membre"] += 1
                days = (now - member.joined_at).days if member.joined_at else 0
                for f_key, f_info in self.features_def.items():
                    if f_info["cat"] == "time" and days >= f_info["days"]:
                        counts[f_key] += 1
                
                if self.check_member_tag(member, target_tag):
                    counts["guild_tag"] += 1

                for p_key in ["discord_url", "site_url"]:
                    kw = settings.get(p_key, "")
                    if kw and self.check_support_status(member, kw):
                        counts[p_key] += 1
        return counts

    async def create_embed(self, guild: discord.Guild, user: discord.Member, sub_menu: str = None) -> discord.Embed:
        """Génère l'affichage visuel synchronisé."""
        gid = str(guild.id)
        config = self.get_or_load_data(gid)
        target_tag = self.resolve_expected_tag(guild, config)
        
        if sub_menu:
            title = f"⚙️ Liaison : {self.features_def[sub_menu]['label']}"
            desc = f"Choisissez le rôle à associer pour le module **{self.features_def[sub_menu]['label']}**."
        else:
            counts = await self.calculate_eligible_counts(guild, config)
            title = "⚙️ Configuration AutoRole Premium"
            desc = f"Gestion globale en temps réel.\n🎯 **Tag ciblé (Analyse alternative active) :** `{target_tag.upper()}`"

        if HAS_MANAGER and config_manager:
            embed = config_manager.get_formatted_embed(guild, user, self.bot, title, desc, guild.id)
        else:
            embed = discord.Embed(title=title, description=desc, color=0x2b2d31)

        if not sub_menu:
            categories = {
                "base": "👥 Structure de Base", 
                "time": "⏳ Récompenses d'Ancienneté", 
                "tag": "🛡️ Intégration Clan / Guilde", 
                "presence": "🎯 Soutien de Statut"
            }
            for cat_key, cat_name in categories.items():
                lines = []
                for f_key, f_info in self.features_def.items():
                    if f_info["cat"] == cat_key:
                        is_active = f_key in config["enabled_features"]
                        role_id = config["roles"].get(f_key)
                        
                        role_obj = guild.get_role(int(role_id)) if role_id and role_id.isdigit() else None
                        r_mention = role_obj.mention if role_obj else "*Aucun rôle lié (Cliquez sur initialiser)*"
                        
                        extra = ""
                        if cat_key == "presence":
                            kw = config["settings"].get(f_key, "")
                            extra = f" ➜ `{kw}`" if kw else " ➜ ⚠️ *Non configuré*"
                        elif cat_key == "tag":
                            lbl_forced = config['settings'].get('forced_tag', 'Aucun')
                            extra = f" *(Forcé: `{lbl_forced}`)*"

                        status = "✅" if is_active else "❌"
                        label_clean = f_info['label'].replace(" [WIP]", "")
                        lines.append(f"{status} `[{counts[f_key]} 👤]` {label_clean.split(' ', 1)[-1]} : {r_mention}{extra}")
                if lines:
                    embed.add_field(name=cat_name, value="\n".join(lines), inline=False)
                
        return embed

# ==============================================================================
# 🎛️ COMPOSANTS INTERFACE GRAPHIQUE DISCORD (UI V2)
# ==============================================================================
class DashboardView(discord.ui.View):
    def __init__(self, cog: AutoRole, guild: discord.Guild):
        super().__init__(timeout=300)
        self.cog, self.guild = cog, guild
        self.setup_components()

    def setup_components(self):
        self.clear_items()
        self.add_item(ModuleToggleSelect(self.cog, self.guild))
        self.add_item(NavigationMenuSelect(self.cog, self.guild))
        self.add_item(KeywordConfigButton(self.cog, self.guild))
        self.add_item(InitializeRolesButton(self.cog, self.guild))  # Option de création réintroduite
        self.add_item(ForceScanButton(self.cog, self.guild))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Droits administratifs insuffisants.", ephemeral=True)
            return False
        return True

    async def refresh(self, interaction: discord.Interaction):
        self.setup_components()
        embed = await self.cog.create_embed(self.guild, interaction.user)
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

class RoleSelectionView(discord.ui.View):
    def __init__(self, cog: AutoRole, guild: discord.Guild, feature_key: str):
        super().__init__(timeout=300)
        self.add_item(NativeRoleSelect(cog, guild, feature_key))
        self.add_item(BackButton(cog, guild))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator

# --- ELEMENTS DE CONTROLE INTERACTIFS ---
class ModuleToggleSelect(discord.ui.Select):
    def __init__(self, cog: AutoRole, guild: discord.Guild):
        self.cog, self.guild = cog, guild
        active = cog.server_data[str(guild.id)].get("enabled_features", [])
        opts = [discord.SelectOption(label=fi["label"].replace(" [WIP]", "").split(' ', 1)[-1], value=fk, default=fk in active) for fk, fi in cog.features_def.items()]
        super().__init__(placeholder="📌 Activer / Désactiver les modules", min_values=0, max_values=len(opts), options=opts[:25], row=0)

    async def callback(self, interaction: discord.Interaction):
        self.cog.server_data[str(self.guild.id)]["enabled_features"] = self.values
        self.cog.save_data(str(self.guild.id))
        self.cog.bot.loop.create_task(self.cog.apply_roles_to_all(self.guild))
        await self.view.refresh(interaction)

class NavigationMenuSelect(discord.ui.Select):
    def __init__(self, cog: AutoRole, guild: discord.Guild):
        self.cog, self.guild = cog, guild
        opts = [discord.SelectOption(label=f"Lier : {fi['label'].replace(' [WIP]', '').split(' ', 1)[-1]}", value=fk, emoji="🆔") for fk, fi in cog.features_def.items()]
        super().__init__(placeholder="🆔 Assigner manuellement un rôle existant", options=opts[:25], row=1)

    async def callback(self, interaction: discord.Interaction):
        fk = self.values[0]
        new_view = RoleSelectionView(self.cog, self.guild, fk)
        embed = await self.cog.create_embed(self.guild, interaction.user, sub_menu=fk)
        await interaction.response.edit_message(embed=embed, view=new_view)

class NativeRoleSelect(discord.ui.RoleSelect):
    def __init__(self, cog: AutoRole, guild: discord.Guild, feature_key: str):
        super().__init__(placeholder="🎨 Choisissez le rôle dans la liste...", min_values=1, max_values=1, row=0)
        self.cog, self.guild, self.feature_key = cog, guild, feature_key

    async def callback(self, interaction: discord.Interaction):
        role = self.values[0]
        bot_member = self.guild.get_member(self.cog.bot.user.id)
        if bot_member and role.position >= bot_member.top_role.position:
            return await interaction.response.send_message(f"❌ Position hiérarchique du rôle supérieure au bot.", ephemeral=True)

        self.cog.server_data[str(self.guild.id)]["roles"][self.feature_key] = str(role.id)
        self.cog.save_data(str(self.guild.id))
        
        new_view = DashboardView(self.cog, self.guild)
        embed = await self.cog.create_embed(self.guild, interaction.user)
        self.cog.bot.loop.create_task(self.cog.apply_roles_to_all(self.guild))
        await interaction.response.edit_message(embed=embed, view=new_view)

class BackButton(discord.ui.Button):
    def __init__(self, cog: AutoRole, guild: discord.Guild):
        super().__init__(label="Retour", style=discord.ButtonStyle.secondary, emoji="🔙", row=1)
        self.cog, self.guild = cog, guild

    async def callback(self, interaction: discord.Interaction):
        new_view = DashboardView(self.cog, self.guild)
        embed = await self.cog.create_embed(self.guild, interaction.user)
        await interaction.response.edit_message(embed=embed, view=new_view)

class KeywordConfigButton(discord.ui.Button):
    def __init__(self, cog: AutoRole, guild: discord.Guild):
        super().__init__(label="Filtres & Tags", style=discord.ButtonStyle.primary, emoji="✍️", row=2)
        self.cog, self.guild = cog, guild

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(KeywordConfigModal(self.cog, self.guild, self.view))

class InitializeRolesButton(discord.ui.Button):
    """L'OPTION DEMANDÉE : Crée instantanément tous les rôles par défaut absents du serveur."""
    def __init__(self, cog: AutoRole, guild: discord.Guild):
        super().__init__(label="Créer/Initialiser les Rôles", style=discord.ButtonStyle.blurple, emoji="🏗️", row=2)
        self.cog, self.guild = cog, guild

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        data = self.cog.get_or_load_data(str(self.guild.id))
        
        creations = 0
        for f_key in self.cog.features_def.keys():
            r_id = data["roles"].get(f_key)
            role_obj = self.guild.get_role(int(r_id)) if r_id and r_id.isdigit() else None
            
            if not role_obj:
                await self.cog.ensure_role_exists(self.guild, f_key)
                creations += 1
                
        await self.cog.apply_roles_to_all(self.guild)
        await self.view.refresh(interaction)
        await interaction.followup.send(f"✅ Infrastructure mise à niveau : **{creations}** rôles configurés.", ephemeral=True)

class ForceScanButton(discord.ui.Button):
    def __init__(self, cog: AutoRole, guild: discord.Guild):
        super().__init__(label="Forcer le Scan complet", style=discord.ButtonStyle.success, emoji="🔄", row=2)
        self.cog, self.guild = cog, guild

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.cog.apply_roles_to_all(self.guild)
        await self.view.refresh(interaction)

class KeywordConfigModal(discord.ui.Modal, title="Filtres Textuels"):
    def __init__(self, cog: AutoRole, guild: discord.Guild, view: discord.ui.View):
        super().__init__()
        self.cog, self.guild, self.parent_view = cog, guild, view
        settings = cog.server_data[str(guild.id)].get("settings", {})

        self.tag_input = discord.ui.TextInput(
            label="Tag de Guilde (Option Alternative)", default=settings.get("forced_tag", ""), 
            placeholder="Ex: Synk", required=False
        )
        self.discord_input = discord.ui.TextInput(
            label="Lien Discord (Soutien)", default=settings.get("discord_url", ""), 
            placeholder="Ex: .gg/synk", required=False
        )
        self.site_input = discord.ui.TextInput(
            label="Lien Site Web (Soutien)", default=settings.get("site_url", ""), 
            placeholder="Ex: synk.fr", required=False
        )

        self.add_item(self.tag_input)
        self.add_item(self.discord_input)
        self.add_item(self.site_input)

    async def on_submit(self, interaction: discord.Interaction):
        gid = str(self.guild.id)
        self.cog.server_data[gid]["settings"]["forced_tag"] = self.tag_input.value.strip()
        self.cog.server_data[gid]["settings"]["discord_url"] = self.discord_input.value.strip()
        self.cog.server_data[gid]["settings"]["site_url"] = self.site_input.value.strip()
        self.cog.save_data(gid)
        
        self.cog.bot.loop.create_task(self.cog.apply_roles_to_all(self.guild))
        await self.parent_view.refresh(interaction)

async def setup(bot: commands.Bot):
    await bot.add_cog(AutoRole(bot))