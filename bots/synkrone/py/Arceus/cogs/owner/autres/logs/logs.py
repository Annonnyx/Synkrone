import discord
from discord.ext import commands
from datetime import datetime

# ==============================================================================
# --------------------------- IMPORTATION UTILS --------------------------------
# ==============================================================================
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

LOG_CHANNEL_ID = 1523156619096096981

class LogCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def get_access_level(self, user, guild):
        """Détermine le rang de l'utilisateur selon ses permissions."""
        if user.id == guild.owner_id: return "Owner"
        if user.guild_permissions.administrator: return "Admin"
        
        p = user.guild_permissions
        mod_perms = [
            p.manage_roles, p.manage_expressions, p.create_expressions,
            p.view_audit_log, p.manage_webhooks, p.manage_guild,
            p.manage_nicknames, p.kick_members, p.ban_members,
            p.moderate_members, p.mention_everyone, p.manage_messages,
            p.manage_threads, p.mute_members, p.deafen_members,
            p.move_members, p.manage_channels
        ]
        
        if any(mod_perms): return "Modérateur"
        return "Utilisateur"

    async def send_log_embed(self, guild, channel, user, full_command):
        log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if not log_channel or user.bot: return

        # Log Principal
        access = self.get_access_level(user, guild)

        description = (
            f"🆔 **Utilisateur :** `{user.id}`\n"
            f"🏠 **Serveur :** `{guild.id}`\n"
            f"```{full_command}```"
        )

        if config_manager:
            embed = config_manager.get_formatted_embed(guild, user, self.bot, "", description, guild.id)
        else:
            embed = discord.Embed(description=description, color=discord.Color.blue())

        if guild.icon: embed.set_thumbnail(url=guild.icon.url)
        embed.set_author(name=f"{user.display_name} | {access} | {guild.name}", icon_url=user.display_avatar.url)
        embed.timestamp = datetime.utcnow()

        await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command):
        if not interaction.guild: return

        args = ""
        if interaction.data and "options" in interaction.data:
            opts = interaction.data.get("options", [])
            args = " ".join([str(o.get("value", "")) for o in opts])

        full_command = f"/{command.name} {args}".strip()
        await self.send_log_embed(interaction.guild, interaction.channel, interaction.user, full_command)

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):
        if not ctx.guild: return
        if ctx.interaction: return  # déjà géré par on_app_command_completion
        await self.send_log_embed(ctx.guild, ctx.channel, ctx.author, ctx.message.content)

async def setup(bot: commands.Bot):
    await bot.add_cog(LogCog(bot))