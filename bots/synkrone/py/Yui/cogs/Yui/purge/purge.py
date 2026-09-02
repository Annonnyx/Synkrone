import discord
from discord.ext import commands
from discord import ui
import asyncio

# ==============================================================================
# --------------------------- IMPORTATION UTILS --------------------------------
# ==============================================================================
try:
    from cogs.developpeur.commands.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# ==============================================================================
# --------------------------- INTERFACE DE PURGE -------------------------------
# ==============================================================================

class PurgeSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Supprimer les rôles", value="roles", emoji="📋", description="Supprime tous les rôles (sauf bot & @everyone)"),
            discord.SelectOption(label="Supprimer les salons vocaux", value="voice", emoji="🔊", description="Supprime l'intégralité des salons vocaux"),
            discord.SelectOption(label="Supprimer les salons textuels", value="text", emoji="💬", description="Supprime salons textuels et catégories"),
            discord.SelectOption(label="Supprimer les emojis", value="emojis", emoji="✨", description="Supprime tous les emojis personnalisés"),
        ]
        super().__init__(
            placeholder="Sélectionnez les éléments à nettoyer...",
            min_values=1,
            max_values=len(options),
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        # On met à jour l'affichage avec les options choisies et on affiche le bouton
        await self.view.update_status(interaction, self.values)

class PurgeView(ui.View):
    def __init__(self, cog, ctx):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.author_id = ctx.author.id
        self.selected_options = []
        
        # Ajout du sélecteur
        self.select_menu = PurgeSelect()
        self.add_item(self.select_menu)
        
        # Bouton de suppression (initialement non ajouté)
        self.confirm_button = ui.Button(label="Démarrer le nettoyage", style=discord.ButtonStyle.danger, emoji="⚠️")
        self.confirm_button.callback = self.start_purge

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Seul l'auteur de la commande peut utiliser ce menu.", ephemeral=True)
            return False
        return True

    async def update_status(self, interaction: discord.Interaction, selected):
        self.selected_options = selected
        
        # Si au moins une option est choisie, on ajoute le bouton s'il n'y est pas
        if len(selected) > 0 and self.confirm_button not in self.children:
            self.add_item(self.confirm_button)
        elif len(selected) == 0 and self.confirm_button in self.children:
            self.remove_item(self.confirm_button)

        # Mise à jour de l'embed
        choices_text = "\n".join([f"• {opt.replace('roles', 'Rôles').replace('voice', 'Salons Vocaux').replace('text', 'Salons Textuels').replace('emojis', 'Emojis')}" for opt in selected])
        embed = self.cog.get_custom_embed(
            interaction, 
            "⚙️ Configuration du Nettoyage", 
            f"Vous avez sélectionné les éléments suivants pour suppression :\n\n**{choices_text}**\n\n*Cliquez sur le bouton rouge pour confirmer.*"
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def start_purge(self, interaction: discord.Interaction):
        # Désactivation immédiate de l'interface pendant le travail
        for item in self.children:
            item.disabled = True
        
        embed = self.cog.get_custom_embed(interaction, "🔄 Purge en cours...", "Le processus de suppression a démarré. Veuillez patienter...")
        await interaction.response.edit_message(embed=embed, view=self)
        
        # Lancement de la logique de suppression
        await self.cog.execute_purge(interaction, self.selected_options)
        
        # Réinitialisation de la vue après la purge
        self.selected_options = []
        self.remove_item(self.confirm_button)
        for item in self.children:
            item.disabled = False
        
        # Message final
        final_embed = self.cog.get_custom_embed(interaction, "✅ Nettoyage Terminé", "Les éléments sélectionnés ont été supprimés avec succès.\nLe sélecteur a été réinitialisé.")
        await interaction.edit_original_response(embed=final_embed, view=self)

# ==============================================================================
# --------------------------- COG PRINCIPAL ------------------------------------
# ==============================================================================

class PurgeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_custom_embed(self, inter, title, description):
        user = inter.user if isinstance(inter, discord.Interaction) else inter.author
        guild = inter.guild
        if config_manager:
            embed = config_manager.get_formatted_embed(
                guild=guild, user=user, bot=self.bot,
                title=title, description=description,
                target_id=guild.id
            )
            # Retrait complet de l'auteur
            embed.remove_author()
        else:
            embed = discord.Embed(title=title, description=description, color=0xff0000)
        
        if self.bot.user.display_avatar:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        return embed

    async def execute_purge(self, interaction: discord.Interaction, options):
        guild = interaction.guild
        
        # 1. Rôles
        if "roles" in options:
            roles_to_del = [r for r in guild.roles if not r.managed and not r.is_default() and r < guild.me.top_role]
            for r in roles_to_del:
                try: 
                    await r.delete(reason="Purge command")
                    await asyncio.sleep(0.3)
                except discord.Forbidden:
                    print(f"[PURGE] Permission refusée pour supprimer le rôle {r.name}")
                except discord.HTTPException as e:
                    print(f"[PURGE] Erreur HTTP en supprimant le rôle {r.name}: {e}")
                except Exception as e:
                    print(f"[PURGE] Erreur inconnue en supprimant le rôle {r.name}: {e}")
                    continue

        # 2. Salons Vocaux
        if "voice" in options:
            voice_channels = guild.voice_channels.copy()  # Copie pour éviter les modifications pendant l'itération
            for v_ch in voice_channels:
                try: 
                    await v_ch.delete(reason="Purge command")
                    await asyncio.sleep(0.3)
                except discord.Forbidden:
                    print(f"[PURGE] Permission refusée pour supprimer le salon vocal {v_ch.name}")
                except discord.HTTPException as e:
                    print(f"[PURGE] Erreur HTTP en supprimant le salon vocal {v_ch.name}: {e}")
                except Exception as e:
                    print(f"[PURGE] Erreur inconnue en supprimant le salon vocal {v_ch.name}: {e}")
                    continue

        # 3. Salons Textuels, Forums, Annonces & Catégories
        if "text" in options:
            # Suppression des salons textuels (hors log ou canal actuel si possible)
            text_channels = guild.text_channels.copy()
            for t_ch in text_channels:
                if t_ch.id == interaction.channel_id:
                    continue  # On ne supprime pas le salon où on est tout de suite
                try:
                    await t_ch.delete(reason="Purge command")
                    await asyncio.sleep(0.3)
                except discord.Forbidden:
                    print(f"[PURGE] Permission refusée pour supprimer le salon textuel {t_ch.name}")
                except discord.HTTPException as e:
                    print(f"[PURGE] Erreur HTTP en supprimant le salon textuel {t_ch.name}: {e}")
                except Exception as e:
                    print(f"[PURGE] Erreur inconnue en supprimant le salon textuel {t_ch.name}: {e}")
                    continue

            # Suppression des salons d'annonces (news channels)
            news_channels = [ch for ch in guild.channels if isinstance(ch, discord.TextChannel) and ch.is_news()]
            for n_ch in news_channels:
                try:
                    await n_ch.delete(reason="Purge command (news channel)")
                    await asyncio.sleep(0.3)
                except discord.Forbidden:
                    print(f"[PURGE] Permission refusée pour supprimer le salon d'annonces {n_ch.name}")
                except discord.HTTPException as e:
                    print(f"[PURGE] Erreur HTTP en supprimant le salon d'annonces {n_ch.name}: {e}")
                except Exception as e:
                    print(f"[PURGE] Erreur inconnue en supprimant le salon d'annonces {n_ch.name}: {e}")
                    continue

            # Suppression des salons forums (ChannelType.forum)
            forum_channels = [ch for ch in guild.channels if ch.type == discord.ChannelType.forum]
            for f_ch in forum_channels:
                try:
                    await f_ch.delete(reason="Purge command (forum)")
                    await asyncio.sleep(0.3)
                except discord.Forbidden:
                    print(f"[PURGE] Permission refusée pour supprimer le salon forum {f_ch.name}")
                except discord.HTTPException as e:
                    print(f"[PURGE] Erreur HTTP en supprimant le salon forum {f_ch.name}: {e}")
                except Exception as e:
                    print(f"[PURGE] Erreur inconnue en supprimant le salon forum {f_ch.name}: {e}")
                    continue

            # Suppression des catégories
            categories = guild.categories.copy()
            for cat in categories:
                try:
                    await cat.delete(reason="Purge command")
                    await asyncio.sleep(0.3)
                except discord.Forbidden:
                    print(f"[PURGE] Permission refusée pour supprimer la catégorie {cat.name}")
                except discord.HTTPException as e:
                    print(f"[PURGE] Erreur HTTP en supprimant la catégorie {cat.name}: {e}")
                except Exception as e:
                    print(f"[PURGE] Erreur inconnue en supprimant la catégorie {cat.name}: {e}")
                    continue

        # 4. Emojis
        if "emojis" in options:
            emojis = guild.emojis.copy()  # Copie pour éviter les modifications pendant l'itération
            for emoji in emojis:
                try: 
                    await emoji.delete(reason="Purge command")
                    await asyncio.sleep(0.2)
                except discord.Forbidden:
                    print(f"[PURGE] Permission refusée pour supprimer l'emoji {emoji.name}")
                except discord.HTTPException as e:
                    print(f"[PURGE] Erreur HTTP en supprimant l'emoji {emoji.name}: {e}")
                except Exception as e:
                    print(f"[PURGE] Erreur inconnue en supprimant l'emoji {emoji.name}: {e}")
                    continue

    @commands.hybrid_command(name="purge", description="Nettoie chirurgicalement des parties du serveur")
    @commands.has_permissions(administrator=True)
    async def purge(self, ctx):
        embed = self.get_custom_embed(
            ctx, 
            "🧹 Nettoyage du Serveur", 
            "Choisissez les catégories d'éléments que vous souhaitez supprimer définitivement du serveur.\n\n*Attention : ces actions sont irréversibles.*"
        )
        await ctx.send(embed=embed, view=PurgeView(self, ctx))

async def setup(bot):
    await bot.add_cog(PurgeCog(bot))