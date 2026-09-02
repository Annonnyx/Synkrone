import discord
from discord import ui, app_commands
from discord.ext import commands
import traceback
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# ==============================================================================
# --- IMPORTS MÉTIER VAX ---
# Utilisation stricte de l'écosystème pour garantir l'homogénéité globale.
# ==============================================================================
try:
    from utils.config_data import DataManager
    from utils.config_theme import config_manager
    from utils.config_perm import ensure_command_permission, perm_command
    from utils.config_emoji import Emoji as E
    HAS_VAX_CORE = True
except ImportError as e:
    HAS_VAX_CORE = False
    print(f"\033[91m[ERREUR CRITIQUE] Impossible d'importer le noyau Vax : {e}\033[0m")

# ==============================================================================
# --- CONFIGURATION GLOBALE & DÉBOGAGE ---
# ==============================================================================
DEBUG_LOGS = True
ERROR_LOGS_ONLY = False

# ==============================================================================
# --- CENTRALISATION DES EMOJIS (UTF-8 NETTOYÉ) ---
# ==============================================================================
E_ON = getattr(E, 'VALIDER', "🟢") if HAS_VAX_CORE else "🟢"
E_OFF = getattr(E, 'REFUSER', "🔴") if HAS_VAX_CORE else "🔴"
E_WARN = getattr(E, 'ATTENTION', "⚠️") if HAS_VAX_CORE else "⚠️"
E_GEAR = getattr(E, 'MODIFIER', "⚙️") if HAS_VAX_CORE else "⚙️"
E_ADD = getattr(E, 'AJOUTER', "➕") if HAS_VAX_CORE else "➕"
E_EDIT = getattr(E, 'MODIFIER', "✏️") if HAS_VAX_CORE else "✏️"
E_TRASH = getattr(E, 'SUPPRIMER', "🗑️") if HAS_VAX_CORE else "🗑️"
E_BACK = getattr(E, 'RETOUR', "↩️") if HAS_VAX_CORE else "↩️"
E_USER = getattr(E, 'PROFIL', "👤") if HAS_VAX_CORE else "👤"
E_CROWN = getattr(E, 'CLASSEMENT', "🏆") if HAS_VAX_CORE else "🏆"
E_RIGHT = getattr(E, 'FLECHE_DROITE', "➡️") if HAS_VAX_CORE else "➡️"
E_LEFT = getattr(E, 'FLECHE_GAUCHE', "⬅️") if HAS_VAX_CORE else "⬅️"
E_CLOCK = getattr(E, 'HORLOGE', "🕒") if HAS_VAX_CORE else "🕒"
E_BOOK = getattr(E, 'HISTOIRE', "📚") if HAS_VAX_CORE else "📚"
E_MEDAL = "🎖️"
E_PALETTE = "🎨"
E_EYE = "👁️"
E_PUZZLE = "🧩"
E_LINK = getattr(E, 'LIEN', "🔗") if HAS_VAX_CORE else "🔗"
E_ROBOT = "🤖"
E_INBOX = "📥"
E_SEARCH = getattr(E, 'RECHERCHE', "🔍") if HAS_VAX_CORE else "🔍"

DEFAULT_TEMPLATE = "**{inviter_name}** a invité {@invited} & comptabilise **{inviter_count} invitations**."

# ==============================================================================
# --- UTILITAIRES DE LOGS & TEMPS ---
# ==============================================================================
def log_sys(action: str, message: str, is_error: bool = False):
    if ERROR_LOGS_ONLY and not is_error: return
    if not DEBUG_LOGS and not is_error: return
    color = "\033[91m" if is_error else "\033[96m"
    prefix = "[ERREUR Invites]" if is_error else "[INFO Invites]"
    print(f"{color}{prefix} [{action}] {message}\033[0m")

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value: return None
    try: return datetime.fromisoformat(value)
    except: return None

def format_presence_duration(since: datetime, now: Optional[datetime] = None) -> str:
    now = now or utcnow()
    delta = now - since
    total_seconds = max(0, int(delta.total_seconds()))

    minute, hour, day = 60, 3600, 86400
    if total_seconds < hour:
        mins = max(1, total_seconds // minute)
        return f"depuis {mins} minute{'s' if mins > 1 else ''}"
    if total_seconds < day:
        hours = total_seconds // hour
        return f"depuis {hours} heure{'s' if hours > 1 else ''}"

    days = total_seconds // day
    months = days // 30
    rem_days = days % 30

    if months <= 0: return f"depuis {days} jour{'s' if days > 1 else ''}"
    if rem_days <= 0: return f"depuis {months} mois"
    return f"depuis {months} mois et {rem_days} jour{'s' if rem_days > 1 else ''}"

# ==============================================================================
# --- GESTIONNAIRE DE DONNÉES (DataManager) ---
# ==============================================================================
class InvitationManager:
    def __init__(self):
        if HAS_VAX_CORE:
            self.data = DataManager("public/statistiques/invitations")
        else:
            log_sys("INIT", "DataManager introuvable. Échec système.", is_error=True)

    def get_default_config(self):
        return {
            "config": {
                "channel_id": None,
                "message_template": DEFAULT_TEMPLATE,
                "use_embed": False,
            },
            "role_rewards": [],
            "inviters": {},
            "invited_users": {},
            "profile_prefs": {}
        }

    def load(self, guild_id: int) -> dict:
        try:
            raw = self.data.load(guild_id) or {}
            default = self.get_default_config()
            for k, v in default.items():
                if k not in raw:
                    raw[k] = v
            return raw
        except Exception as e:
            log_sys("DB_LOAD", f"Erreur de lecture DB pour {guild_id}: {e}\n{traceback.format_exc()}", is_error=True)
            return self.get_default_config()

    def save(self, guild_id: int, config: dict):
        try:
            self.data.save(guild_id, config)
        except Exception as e:
            log_sys("DB_SAVE", f"Erreur d'écriture DB pour {guild_id}: {e}", is_error=True)

inv_db = InvitationManager()

# ==============================================================================
# --- MODALS D'INTERACTION ---
# ==============================================================================
class ProfileLookupModal(ui.Modal, title="🔍 Recherche de Profil"):
    target_id = ui.TextInput(label="ID utilisateur", placeholder="Ex: 123456789012345678", required=True, min_length=17, max_length=20)
    
    def __init__(self, view: "InvitationLayoutView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.target_id.value.strip()
        if not raw.isdigit():
            if not interaction.response.is_done(): await interaction.response.defer()
            return await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, ID invalide.", delete_after=6)

        self.view.target_id = int(raw)
        self.view.mode = "profile"
        self.view.status_message = f"{E_ON} Profil cible mis à jour."
        await self.view._refresh(interaction)

class ConfigModal(ui.Modal, title="⚙️ Configuration Invitations"):
    def __init__(self, view: "InvitationLayoutView"):
        super().__init__()
        self.view = view
        data = inv_db.load(view.guild.id)
        cfg = data["config"]

        self.c = ui.TextInput(label="ID du Salon de notification", placeholder="Laissez vide pour désactiver", required=False, max_length=20, default=str(cfg.get("channel_id") or ""))
        self.t = ui.TextInput(label="Message personnalisé", placeholder=DEFAULT_TEMPLATE, required=False, style=discord.TextStyle.long, max_length=1000, default=cfg.get("message_template") or DEFAULT_TEMPLATE)
        self.add_item(self.c)
        self.add_item(self.t)

    async def on_submit(self, interaction: discord.Interaction):
        data = inv_db.load(self.view.guild.id)
        raw_c = self.c.value.strip()
        
        if raw_c and not raw_c.isdigit():
            if not interaction.response.is_done(): await interaction.response.defer()
            return await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, le salon doit être un ID numérique.", delete_after=6)
            
        data["config"]["channel_id"] = int(raw_c) if raw_c else None
        data["config"]["message_template"] = self.t.value.strip() or DEFAULT_TEMPLATE
        inv_db.save(self.view.guild.id, data)
        
        self.view.status_message = f"{E_ON} Configuration globale mise à jour."
        await self.view._refresh(interaction)

class RewardAddModal(ui.Modal, title="➕ Ajouter une récompense"):
    r_id = ui.TextInput(label="ID du rôle", placeholder="Ex: 123456789012345678", required=True, max_length=20)
    req = ui.TextInput(label="Invités actifs requis", placeholder="Ex: 5", required=True, max_length=4)
    
    def __init__(self, view: "InvitationLayoutView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        data = inv_db.load(self.view.guild.id)
        rewards = data.get("role_rewards", [])
        
        if len(rewards) >= 25:
            if not interaction.response.is_done(): await interaction.response.defer()
            return await interaction.channel.send(f"{E_WARN} {interaction.user.mention}, limite de 25 récompenses atteinte.", delete_after=6)

        raw_r, raw_req = self.r_id.value.strip(), self.req.value.strip()
        if not raw_r.isdigit() or not raw_req.isdigit() or int(raw_req) < 1:
            if not interaction.response.is_done(): await interaction.response.defer()
            return await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, valeurs invalides.", delete_after=6)

        used_slots = {int(r.get("slot", 0)) for r in rewards}
        slot = next((i for i in range(1, 26) if i not in used_slots), 1)
        
        rewards.append({"slot": slot, "enabled": True, "role_id": int(raw_r), "required_invites": int(raw_req)})
        data["role_rewards"] = sorted(rewards, key=lambda x: int(x.get("slot", 0)))
        inv_db.save(self.view.guild.id, data)
        
        await self.view.cog.refresh_role_rewards(self.view.guild)
        self.view.selected_slot = slot
        self.view.status_message = f"{E_ON} Récompense #{slot} ajoutée."
        await self.view._refresh(interaction)

class RewardEditModal(ui.Modal, title="✏️ Modifier la récompense"):
    def __init__(self, view: "InvitationLayoutView"):
        super().__init__()
        self.view = view
        data = inv_db.load(view.guild.id)
        reward = next((r for r in data.get("role_rewards", []) if int(r.get("slot", 0)) == view.selected_slot), None)
        
        self.r_id = ui.TextInput(label="ID du rôle", required=True, max_length=20, default=str(reward.get("role_id")) if reward else "")
        self.req = ui.TextInput(label="Invités requis", required=True, max_length=4, default=str(reward.get("required_invites", 1)) if reward else "1")
        self.en = ui.TextInput(label="Actif ? (oui/non)", required=True, max_length=3, default="oui" if (reward and reward.get("enabled", True)) else "non")
        
        self.add_item(self.r_id)
        self.add_item(self.req)
        self.add_item(self.en)

    async def on_submit(self, interaction: discord.Interaction):
        data = inv_db.load(self.view.guild.id)
        rewards = data.get("role_rewards", [])
        idx = next((i for i, r in enumerate(rewards) if int(r.get("slot", 0)) == self.view.selected_slot), None)
        
        if idx is None:
            if not interaction.response.is_done(): await interaction.response.defer()
            return await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, récompense introuvable.", delete_after=6)

        raw_r, raw_req, raw_en = self.r_id.value.strip(), self.req.value.strip(), self.en.value.strip().lower()
        if not raw_r.isdigit() or not raw_req.isdigit() or int(raw_req) < 1:
            if not interaction.response.is_done(): await interaction.response.defer()
            return await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, valeurs invalides.", delete_after=6)

        rewards[idx].update({"role_id": int(raw_r), "required_invites": int(raw_req), "enabled": raw_en in ("oui", "o", "yes", "y", "1", "on")})
        inv_db.save(self.view.guild.id, data)
        
        await self.view.cog.refresh_role_rewards(self.view.guild)
        self.view.status_message = f"{E_ON} Récompense modifiée avec succès."
        await self.view._refresh(interaction)

# ==============================================================================
# --- VUE PRINCIPALE (Layout V2 MACHINE & ETATS) ---
# ==============================================================================
class InvitationLayoutView(ui.LayoutView):
    def __init__(self, cog: "InvitationCog", guild: discord.Guild, user: discord.Member, target_id: int = None, mode: str = "profile"):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild = guild
        self.user = user
        self.target_id = target_id or user.id
        self.mode = mode
        self.lb_page = 1
        self.selected_slot = None
        self.status_message = ""
        self._build()

    def _has_admin_perm(self) -> bool:
        """Vérifie si l'utilisateur est administrateur ou a la permission de gestion du serveur."""
        perms = getattr(self.user, "guild_permissions", None)
        if not perms:
            return False
        return perms.administrator or perms.manage_guild

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            if not interaction.response.is_done(): await interaction.response.defer()
            await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, cette console est protégée.", delete_after=6)
            return False
        return True

    def _build(self):
        try:
            log_sys("BUILD", f"Construction de la vue (Mode: {self.mode})")
            self.clear_items()
            
            accent_color = 0x2b2d31
            footer_text = ""
            if HAS_VAX_CORE and config_manager:
                try:
                    theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.cog.bot)
                    accent_color = int(theme.get("color", 0x2b2d31))
                    footer_text = theme.get("footer_text", "")
                except Exception as e:
                    log_sys("THEME_ERR", f"Erreur thème: {e}", is_error=True)

            container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
            
            if self.status_message:
                container.add_item(ui.TextDisplay(f"> {self.status_message}"))
                self.status_message = ""

            # Aiguillage du contenu principal
            if self.mode == "profile": self._build_profile(container)
            elif self.mode == "leaderboard": self._build_leaderboard(container)
            elif self.mode == "config": self._build_config(container)
            elif self.mode == "rewards": self._build_rewards(container)
            elif self.mode == "vars": self._build_vars(container)

            # Ligne 1 : Navigation Globale
            nav_row = ui.ActionRow()
            btn_prof = ui.Button(label="Profil", style=discord.ButtonStyle.primary if self.mode == "profile" else discord.ButtonStyle.secondary, emoji=E_USER)
            btn_prof.callback = lambda i: self._change_mode(i, "profile")
            nav_row.add_item(btn_prof)

            btn_lb = ui.Button(label="Classement", style=discord.ButtonStyle.primary if self.mode == "leaderboard" else discord.ButtonStyle.secondary, emoji=E_CROWN)
            btn_lb.callback = lambda i: self._change_mode(i, "leaderboard")
            nav_row.add_item(btn_lb)

            # Condition de permission assouplie (Admin OU Gérer le serveur)
            if self._has_admin_perm():
                btn_cfg = ui.Button(label="Configuration", style=discord.ButtonStyle.success if self.mode in ["config", "rewards", "vars"] else discord.ButtonStyle.secondary, emoji=E_GEAR)
                btn_cfg.callback = lambda i: self._change_mode(i, "config")
                nav_row.add_item(btn_cfg)

            container.add_item(nav_row)

            # Lignes 2+ : Contrôles spécifiques
            self._build_controls(container)

            if footer_text:
                container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
                container.add_item(ui.TextDisplay(footer_text))

            self.add_item(container)
        except Exception as e:
            log_sys("BUILD_ERR", f"Erreur critique lors de la construction UI:\n{traceback.format_exc()}", is_error=True)

    async def _refresh(self, interaction: discord.Interaction):
        try:
            self._build()
            if interaction.response.is_done():
                await interaction.edit_original_response(view=self)
            else:
                await interaction.response.edit_message(view=self)
        except Exception as e:
            log_sys("REFRESH_ERR", f"Échec actualisation UI: {e}", is_error=True)

    async def _change_mode(self, interaction: discord.Interaction, new_mode: str):
        self.mode = new_mode
        self.status_message = ""
        if new_mode == "profile": self.target_id = self.user.id
        await self._refresh(interaction)

    # --- MÉTHODES DE CONSTRUCTION DE SECTIONS ---
    def _build_profile(self, container: ui.Container):
        data = inv_db.load(self.guild.id)
        t_user = self.guild.get_member(self.target_id)
        disp_name = t_user.display_name if t_user else str(self.target_id)
        av_url = t_user.display_avatar.url if t_user and hasattr(t_user, "display_avatar") else None
        
        invited_users = data.get("invited_users", {})
        inviters = data.get("inviters", {})

        invited_by_rec = invited_users.get(str(self.target_id), {})
        invited_by = invited_by_rec.get("inviter_id")
        invited_by_name = invited_by_rec.get("inviter_name")
        invited_by_member = self.guild.get_member(int(invited_by)) if invited_by else None
        
        if invited_by_member: ib_txt = invited_by_member.mention
        elif invited_by: ib_txt = f"<@{int(invited_by)}>"
        elif invited_by_name: ib_txt = f"`{invited_by_name}`"
        else: ib_txt = "Inconnu"

        invited_records = [(uid, rec) for uid, rec in invited_users.items() if str(rec.get("inviter_id")) == str(self.target_id)]
        bots_inv = sum(1 for _, r in invited_records if r.get("is_bot"))
        
        present_humans = []
        for uid, rec in invited_records:
            if rec.get("is_bot"): continue
            isp = rec.get("is_present")
            if isp is None: isp = bool(self.guild.get_member(int(uid)))
            if isp:
                m = self.guild.get_member(int(uid))
                present_humans.append((m.mention if m else f"<@{uid}>", rec))

        pres_count = len(present_humans)
        now = utcnow()

        def older_than(rec, days):
            j = parse_dt(rec.get("joined_at"))
            return bool(j and (now - j).days >= days)

        d7 = sum(1 for _, r in present_humans if older_than(r, 7))
        d30 = sum(1 for _, r in present_humans if older_than(r, 30))
        d365 = sum(1 for _, r in present_humans if older_than(r, 365))

        inviter_stats = inviters.get(str(self.target_id), {})
        total_rec = inviter_stats.get("joined_total", sum(1 for _, r in invited_records if not r.get("is_bot")))

        desc = f"### {E_USER} Profil Invitation de {disp_name}\n"
        if ib_txt != "Inconnu": desc += f"👥 **Invité par** : {ib_txt}\n"
        
        desc += f"\n{E_ROBOT} **Bots invités** : `{bots_inv}`\n"
        desc += f"{E_INBOX} **Ayant rejoint** : `{total_rec}`\n"
        desc += f"{E_ON} **Encore présents** : `{pres_count}`\n\n"

        # Affichage direct par défaut des détails de présence et rétention
        desc += f"**Rétention** :\n- Plus de 7 jours : `{d7}`\n- Plus de 1 mois : `{d30}`\n- Plus de 1 an : `{d365}`\n\n"
            
        newest = sorted(present_humans, key=lambda x: parse_dt(x[1].get("joined_at")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)[:3]
        oldest = sorted(present_humans, key=lambda x: parse_dt(x[1].get("joined_at")) or datetime.max.replace(tzinfo=timezone.utc))[:3]
        
        ntxt = "\n".join(f"- {m} ({format_presence_duration(parse_dt(r.get('joined_at')) or now, now)})" for m, r in newest) if newest else "Aucun"
        otxt = "\n".join(f"- {m} ({format_presence_duration(parse_dt(r.get('joined_at')) or now, now)})" for m, r in oldest) if oldest else "Aucun"
        
        desc += f"**{E_CLOCK} 3 plus récents** :\n{ntxt}\n\n**{E_BOOK} 3 plus anciens** :\n{otxt}"

        try:
            if av_url:
                container.add_item(ui.Section(desc, accessory=ui.Thumbnail(av_url, description="Avatar")))
            else:
                container.add_item(ui.TextDisplay(desc))
        except: 
            container.add_item(ui.TextDisplay(desc))

    def _build_leaderboard(self, container: ui.Container):
        data = inv_db.load(self.guild.id)
        rows = self.cog._get_leaderboard_rows(self.guild, data)
        max_p = self.cog._get_lb_max_page(len(rows))
        self.lb_page = min(max(1, self.lb_page), max_p)
        start, end = self.cog._get_lb_bounds(self.lb_page)
        chunk = rows[start:end]

        v_count = self.cog.active_invites_count(self.guild, data, self.user.id)
        v_pos = next((i + 1 for i, (u, _) in enumerate(rows) if u == self.user.id), None)
        
        desc = f"### {E_CROWN} Classement des Invitations\n"
        desc += f"🙋 **Votre position :** `#{v_pos if v_pos else 'N/C'}` avec `{v_count}` invité(s).\n\n"
        
        if not rows: desc += "> 📍 Aucune donnée disponible."
        else:
            for i, (uid, count) in enumerate(chunk, start=start + 1):
                m = self.guild.get_member(uid)
                mt = m.mention if m else f"<@{uid}>"
                med = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else "🔹"
                desc += f"{med} **#{i}** {mt} - `{count}` invité(s)\n"
            desc += f"\n*Page {self.lb_page}/{max_p}*"
        
        container.add_item(ui.TextDisplay(desc))

    def _build_config(self, container: ui.Container):
        cfg = inv_db.load(self.guild.id)["config"]
        rw = inv_db.load(self.guild.id).get("role_rewards", [])
        
        chan_txt = f"<#{cfg['channel_id']}>" if cfg.get("channel_id") else "`Non configuré`"
        mode_txt = "`LayoutV2`" if cfg.get("use_embed") else "`Message Brut`"
        act_r = sum(1 for r in rw if r.get("enabled"))
        
        desc = (
            f"### {E_GEAR} Configuration Système\n"
            f"**Salon de notification :** {chan_txt}\n"
            f"**Type de rendu :** {mode_txt}\n"
            f"**Récompenses actives :** `{act_r}/{len(rw)}`\n\n"
            f"**Message configuré :**\n```\n{cfg.get('message_template') or DEFAULT_TEMPLATE}\n```"
        )
        container.add_item(ui.TextDisplay(desc))

    def _build_rewards(self, container: ui.Container):
        rw = sorted(inv_db.load(self.guild.id).get("role_rewards", []), key=lambda x: int(x.get("slot",0)))
        desc = f"### {E_MEDAL} Gestion des Récompenses (`{len(rw)}/25`)\n\n"
        
        if not rw: desc += "> Aucune récompense configurée."
        else:
            for r in rw:
                slot, rid, req, en = r.get("slot",0), r.get("role_id"), r.get("required_invites",1), r.get("enabled", True)
                rl = self.guild.get_role(int(rid)) if rid else None
                rt = rl.mention if rl else f"`ID {rid}`"
                mk = "👉" if self.selected_slot == slot else "•"
                st = "✅" if en else "⛔"
                desc += f"{mk} **#{slot}** {st} {rt} - Requis : `{req}`\n"
        
        container.add_item(ui.TextDisplay(desc))

    def _build_vars(self, container: ui.Container):
        t = inv_db.load(self.guild.id)["config"].get("message_template") or DEFAULT_TEMPLATE
        desc = (
            f"### {E_PUZZLE} Lexique des Variables\n"
            "- `{invited}` / `{@invited}` : Ping du nouveau membre\n"
            "- `{invited_name}` : Pseudo du nouveau membre\n"
            "- `{inviter}` / `{@inviter}` : Ping de l'invitant\n"
            "- `{inviter_name}` : Pseudo de l'invitant\n"
            "- `{inviter_count}` : Total des invitations de l'invitant\n"
            "- `{invite_total}` : Total des invitations du serveur\n"
            "- `{invite_code}` : Code du lien utilisé\n\n"
            f"**Aperçu avec le template actuel :**\n"
            f"> *{self.cog.render_template(self.guild, self.user, self.user, 'XyZ123')}*"
        )
        container.add_item(ui.TextDisplay(desc))

    def _build_controls(self, container: ui.Container):
        if self.mode == "profile":
            r1 = ui.ActionRow()
            btn_look = ui.Button(label="Chercher un Profil", style=discord.ButtonStyle.secondary, emoji=E_SEARCH)
            btn_look.callback = lambda i: i.response.send_modal(ProfileLookupModal(self))
            r1.add_item(btn_look)
            container.add_item(r1)

        elif self.mode == "leaderboard":
            r1 = ui.ActionRow()
            btn_prev = ui.Button(label="Page précédente", style=discord.ButtonStyle.secondary, emoji=E_LEFT, disabled=self.lb_page <= 1)
            async def prev_cb(i): 
                if not i.response.is_done(): await i.response.defer()
                self.lb_page -= 1
                await self._refresh(i)
            btn_prev.callback = prev_cb
            r1.add_item(btn_prev)
            
            data = inv_db.load(self.guild.id)
            rows = self.cog._get_leaderboard_rows(self.guild, data)
            max_p = self.cog._get_lb_max_page(len(rows))
            
            btn_next = ui.Button(label="Page suivante", style=discord.ButtonStyle.secondary, emoji=E_RIGHT, disabled=self.lb_page >= max_p)
            async def next_cb(i):
                if not i.response.is_done(): await i.response.defer()
                self.lb_page += 1
                await self._refresh(i)
            btn_next.callback = next_cb
            r1.add_item(btn_next)
            container.add_item(r1)

        elif self.mode == "config":
            r1 = ui.ActionRow()
            opts = [
                discord.SelectOption(label="Modifier Salon + Message", value="edit", emoji=E_EDIT),
                discord.SelectOption(label="Basculer LayoutV2 / Brut", value="toggle", emoji=E_PALETTE),
                discord.SelectOption(label="Gérer les récompenses", value="rw", emoji=E_MEDAL),
                discord.SelectOption(label="Aide Variables", value="vars", emoji=E_PUZZLE)
            ]
            sel = ui.Select(placeholder="Actions de configuration...", options=opts)
            async def cfg_cb(interaction):
                val = interaction.data['values'][0]
                if val == "edit": await interaction.response.send_modal(ConfigModal(self))
                elif val == "toggle":
                    if not interaction.response.is_done(): await interaction.response.defer()
                    d = inv_db.load(self.guild.id)
                    d["config"]["use_embed"] = not bool(d["config"].get("use_embed"))
                    inv_db.save(self.guild.id, d)
                    self.status_message = f"{E_ON} Mode de rendu mis à jour."
                    await self._refresh(interaction)
                elif val == "rw": await self._change_mode(interaction, "rewards")
                elif val == "vars": await self._change_mode(interaction, "vars")
            sel.callback = cfg_cb
            r1.add_item(sel)
            container.add_item(r1)

        elif self.mode == "rewards":
            rw = sorted(inv_db.load(self.guild.id).get("role_rewards", []), key=lambda x: int(x.get("slot",0)))
            r1 = ui.ActionRow()
            opts = [discord.SelectOption(label=f"#{r.get('slot')} - Seuil: {r.get('required_invites')}", value=str(r.get('slot')), default=self.selected_slot==r.get('slot')) for r in rw[:25]]
            if not opts: opts.append(discord.SelectOption(label="Aucune récompense", value="none", emoji=E_WARN))
            sel = ui.Select(placeholder="Sélectionner une récompense...", options=opts)
            async def rw_cb(interaction):
                if not interaction.response.is_done(): await interaction.response.defer()
                val = interaction.data['values'][0]
                self.selected_slot = None if val == "none" else int(val)
                await self._refresh(interaction)
            sel.callback = rw_cb
            r1.add_item(sel)
            container.add_item(r1)

            r2 = ui.ActionRow()
            b_add = ui.Button(label="Ajouter", style=discord.ButtonStyle.success, emoji=E_ADD)
            b_add.callback = lambda i: i.response.send_modal(RewardAddModal(self))
            r2.add_item(b_add)
            
            b_ed = ui.Button(label="Modifier", style=discord.ButtonStyle.primary, emoji=E_EDIT, disabled=not self.selected_slot)
            b_ed.callback = lambda i: i.response.send_modal(RewardEditModal(self))
            r2.add_item(b_ed)
            
            b_del = ui.Button(label="Supprimer", style=discord.ButtonStyle.danger, emoji=E_TRASH, disabled=not self.selected_slot)
            async def del_cb(interaction):
                if not interaction.response.is_done(): await interaction.response.defer()
                d = inv_db.load(self.guild.id)
                d["role_rewards"] = [x for x in d.get("role_rewards",[]) if int(x.get("slot",0)) != self.selected_slot]
                inv_db.save(self.guild.id, d)
                self.selected_slot = None
                self.status_message = f"{E_TRASH} Récompense supprimée."
                await self._refresh(interaction)
            b_del.callback = del_cb
            r2.add_item(b_del)
            
            b_back = ui.Button(label="Retour", style=discord.ButtonStyle.secondary, emoji=E_BACK)
            b_back.callback = lambda i: self._change_mode(i, "config")
            r2.add_item(b_back)
            container.add_item(r2)

        elif self.mode == "vars":
            r1 = ui.ActionRow()
            b_back = ui.Button(label="Retour", style=discord.ButtonStyle.secondary, emoji=E_BACK)
            b_back.callback = lambda i: self._change_mode(i, "config")
            r1.add_item(b_back)
            container.add_item(r1)

# ==============================================================================
# --- COG PRINCIPAL (Moteur des Invitations) ---
# ==============================================================================
class InvitationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.invites_cache: Dict[int, Dict[str, int]] = {}
        self.invites_meta_cache: Dict[int, Dict[str, Dict[str, Any]]] = {}
        self.recently_deleted_invites: Dict[int, Dict[str, Dict[str, Any]]] = {}
        self.vanity_cache: Dict[int, int] = {}
        log_sys("INIT", "Module Invitation V3 déployé.")

    # --- REWARDS LOGIC ---
    async def refresh_role_rewards(self, guild: discord.Guild):
        data = inv_db.load(guild.id)
        rewards = data.get("role_rewards", [])
        if not rewards: return
        
        candidate_ids = set(int(x) for x in data.get("inviters", {}).keys())
        managed_roles = []
        for r in rewards:
            role_id = r.get("role_id")
            if not role_id: continue
            role = guild.get_role(int(role_id))
            if role:
                managed_roles.append((role, r))
                for m in role.members: candidate_ids.add(m.id)

        for uid in candidate_ids:
            member = guild.get_member(uid)
            if not member: continue
            current = self.active_invites_count(guild, data, uid)
            for role, r in managed_roles:
                enabled = bool(r.get("enabled", True))
                required = int(r.get("required_invites") or 1)
                should_have = enabled and current >= required
                has_role = role in member.roles
                try:
                    if should_have and not has_role:
                        await member.add_roles(role, reason="Seuil d'invitations atteint")
                    elif not should_have and has_role:
                        await member.remove_roles(role, reason="Seuil d'invitations non atteint")
                except: pass

    # --- STATS LOGIC ---
    def active_invites_count(self, guild: discord.Guild, data: Dict[str, Any], inviter_id: int) -> int:
        total = 0
        for uid, rec in data.get("invited_users", {}).items():
            if str(rec.get("inviter_id")) != str(inviter_id) or rec.get("is_bot"): continue
            isp = rec.get("is_present")
            if isp is None: isp = bool(guild.get_member(int(uid)))
            if isp: total += 1
        return total

    def _get_leaderboard_rows(self, guild: discord.Guild, data: Dict[str, Any]) -> list[tuple[int, int]]:
        inviters = data.get("inviters", {})
        invited_users = data.get("invited_users", {})
        rows = []
        for inv_id_str in inviters.keys():
            iid = int(inv_id_str)
            rows.append((iid, self.active_invites_count(guild, data, iid)))
        for rec in invited_users.values():
            iid = rec.get("inviter_id")
            if iid and all(int(iid) != rid for rid, _ in rows):
                rows.append((int(iid), self.active_invites_count(guild, data, int(iid))))
        return sorted(rows, key=lambda x: x[1], reverse=True)

    def _get_lb_bounds(self, page: int) -> tuple[int, int]:
        if page <= 1: return 0, 10
        if page == 2: return 10, 50
        start = 50 + (page - 3) * 50
        return start, start + 50

    def _get_lb_max_page(self, total: int) -> int:
        if total <= 10: return 1
        if total <= 50: return 2
        return 2 + ((total - 50 + 49) // 50)

    def total_active_invited_in_guild(self, guild: discord.Guild, data: Dict[str, Any]) -> int:
        return sum(1 for uid, rec in data.get("invited_users", {}).items() if not rec.get("is_bot") and guild.get_member(int(uid)))

    def render_template(self, guild: discord.Guild, inviter: Optional[discord.abc.User], invited: discord.abc.User, invite_code: str, custom_template: Optional[str] = None, inviter_id: Optional[int] = None, inviter_name_override: Optional[str] = None) -> str:
        data = inv_db.load(guild.id)
        template = custom_template if custom_template is not None else (data["config"].get("message_template") or DEFAULT_TEMPLATE)

        eff_id = inviter.id if inviter else inviter_id
        inv_men = inviter.mention if inviter else (f"<@{eff_id}>" if eff_id else "Inconnu")
        inv_nam = inviter.display_name if inviter else (inviter_name_override or (f"Utilisateur {eff_id}" if eff_id else "Inconnu"))

        values = {
            "{inviter}": inv_men, "{@inviter}": inv_men, "{inviter_name}": inv_nam,
            "{invited}": invited.mention, "{@invited}": invited.mention, "{invited_name}": invited.display_name,
            "{invite_total}": str(self.total_active_invited_in_guild(guild, data)),
            "{inviter_count}": str(self.active_invites_count(guild, data, eff_id)) if eff_id else "0",
            "{invite_code}": invite_code or "inconnu",
            "<@invitedname>": invited.mention, "<@invitername>": inv_men, "<@invtername>": inv_men
        }

        text = template
        for k, v in values.items(): text = text.replace(k, v)
        return text

    # --- CACHE LOGIC ---
    def _invite_meta(self, invite: discord.Invite) -> Dict[str, Any]:
        ct = invite.created_at
        return {"inviter_id": invite.inviter.id if invite.inviter else None, "uses": int(invite.uses or 0), "max_uses": invite.max_uses, "created_ts": ct.timestamp() if ct else 0.0}

    async def _get_vanity_uses(self, guild: discord.Guild) -> int:
        code = getattr(guild, "vanity_url_code", None)
        if not code: return 0
        try: return int(getattr(await guild.vanity_invite(), "uses", 0) or 0)
        except: return 0

    async def cache_guild_invites(self, guild: discord.Guild):
        try:
            invites = await guild.invites()
            self.invites_cache[guild.id] = {i.code: i.uses for i in invites}
            self.invites_meta_cache[guild.id] = {i.code: self._invite_meta(i) for i in invites}
        except:
            self.invites_cache[guild.id] = {}
            self.invites_meta_cache[guild.id] = {}
        self.vanity_cache[guild.id] = await self._get_vanity_uses(guild)

    async def detect_used_invite(self, guild: discord.Guild) -> tuple[Optional[str], Optional[int]]:
        old = self.invites_cache.get(guild.id, {})
        old_meta = self.invites_meta_cache.get(guild.id, {})
        old_vanity = self.vanity_cache.get(guild.id, 0)
        
        try: new_invites = await guild.invites()
        except: new_invites = []

        new_map = {i.code: i.uses for i in new_invites}
        self.invites_cache[guild.id] = new_map
        self.invites_meta_cache[guild.id] = {i.code: self._invite_meta(i) for i in new_invites}

        for inv in new_invites:
            if inv.uses > old.get(inv.code, 0):
                return inv.code, inv.inviter.id if inv.inviter else None

        rem = []
        for code, uses in old.items():
            if code not in new_map:
                meta = old_meta.get(code, {})
                if meta.get("max_uses") == 1 and int(uses or 0) == 0:
                    rem.append((code, meta))
        if rem:
            rem.sort(key=lambda x: float(x[1].get("created_ts") or 0.0), reverse=True)
            return rem[0][0], rem[0][1].get("inviter_id")

        now_ts = utcnow().timestamp()
        del_map = self.recently_deleted_invites.get(guild.id, {})
        del_cand = []
        for code, meta in list(del_map.items()):
            if (now_ts - float(meta.get("deleted_ts") or 0.0)) > 60:
                del_map.pop(code, None)
                continue
            if int(meta.get("max_uses") or 0) == 1:
                del_cand.append((code, meta))
        if del_cand:
            del_cand.sort(key=lambda x: float(x[1].get("deleted_ts") or 0.0), reverse=True)
            del_map.pop(del_cand[0][0], None)
            return del_cand[0][0], del_cand[0][1].get("inviter_id")

        vcode = getattr(guild, "vanity_url_code", None)
        if vcode:
            new_v = await self._get_vanity_uses(guild)
            self.vanity_cache[guild.id] = new_v
            if new_v > old_vanity: return vcode, None

        return None, None

    # --- EVENTS ---
    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds: await self.cache_guild_invites(guild)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        await self.cache_guild_invites(guild)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        if invite.guild:
            self.invites_cache.setdefault(invite.guild.id, {})[invite.code] = int(invite.uses or 0)
            self.invites_meta_cache.setdefault(invite.guild.id, {})[invite.code] = self._invite_meta(invite)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        if invite.guild:
            meta = self._invite_meta(invite)
            meta["deleted_ts"] = utcnow().timestamp()
            self.recently_deleted_invites.setdefault(invite.guild.id, {})[invite.code] = meta

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        try:
            guild = member.guild
            code, inviter_id = await self.detect_used_invite(guild)
            inv_u = guild.get_member(inviter_id) if inviter_id else None
            if inviter_id and not inv_u:
                try: inv_u = await self.bot.fetch_user(inviter_id)
                except: pass

            data = inv_db.load(guild.id)
            if inviter_id:
                inv = data["inviters"].setdefault(str(inviter_id), {"joined_total": 0, "bots_total": 0})
                if member.bot: inv["bots_total"] = int(inv.get("bots_total", 0)) + 1
                else: inv["joined_total"] = int(inv.get("joined_total", 0)) + 1

            data["invited_users"][str(member.id)] = {
                "inviter_id": inviter_id, "invite_code": code or "inconnu", "joined_at": utcnow().isoformat(),
                "is_bot": bool(member.bot), "is_present": True, "invited_name": member.display_name,
                "inviter_name": inv_u.display_name if inv_u else None
            }
            inv_db.save(guild.id, data)

            await self.refresh_role_rewards(guild)
            cfg = data.get("config", {})
            cid = cfg.get("channel_id")
            if not cid: return
            chan = guild.get_channel(int(cid))
            if not chan: return

            vcode = getattr(guild, "vanity_url_code", None)
            if vcode and code == vcode and not inv_u:
                txt = f"**{member.display_name}** est arrivé en utilisant l'URL personnalisée **{vcode}**"
            else:
                txt = self.render_template(guild, inv_u, member, code or "inconnu", inviter_id=inviter_id)

            if cfg.get("use_embed"):
                v = ui.LayoutView(timeout=1)
                c = ui.Container(accent_color=discord.Color.blurple(), spoiler=False)
                try: c.add_item(ui.Section(f"### 🎉 Nouvelle Invitation\n{txt}", accessory=ui.Thumbnail(member.display_avatar.url, description="Avatar")))
                except: c.add_item(ui.TextDisplay(f"### 🎉 Nouvelle Invitation\n{txt}"))
                v.add_item(c)
                await chan.send(view=v)
            else:
                await chan.send(txt)
        except Exception as e:
            log_sys("JOIN_ERR", f"Erreur critique on_member_join:\n{traceback.format_exc()}", is_error=True)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        try:
            data = inv_db.load(member.guild.id)
            if str(member.id) in data.get("invited_users", {}):
                data["invited_users"][str(member.id)]["is_present"] = False
                inv_db.save(member.guild.id, data)
            await self.refresh_role_rewards(member.guild)
        except Exception as e:
            log_sys("REMOVE_ERR", f"Erreur on_member_remove:\n{traceback.format_exc()}", is_error=True)

    # --- COMMAND ---
    @perm_command(level=2)
    @commands.hybrid_command(name="invitation", description="Panneau global des invitations (Profil, Classement, Config).")
    async def invitation_cmd(self, ctx: commands.Context):
        try:
            if not ctx.guild: return await ctx.send(f"{E_OFF} Serveur uniquement.")
            
            if HAS_VAX_CORE and not await ensure_command_permission(ctx, command_name="invitation"):
                return
                
            await ctx.defer(ephemeral=False)
            view = InvitationLayoutView(self, ctx.guild, ctx.author, target_id=ctx.author.id, mode="profile")
            await ctx.send(view=view)
        except Exception as e:
            log_sys("CMD_ERR", f"Erreur critique lors du lancement de la commande:\n{traceback.format_exc()}", is_error=True)


async def setup(bot: commands.Bot):
    if bot.get_command("invitation"): bot.remove_command("invitation")
    await bot.add_cog(InvitationCog(bot))