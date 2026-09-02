import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
import datetime
import traceback
from typing import List
from pathlib import Path

# ==============================================================================
# --------------------------- IMPORTATION UTILS --------------------------------
# ==============================================================================
try:
    from cogs.addons.embed_type.utils import config_manager
    HAS_CUSTOM_EMBED = True
except ImportError:
    config_manager = None
    HAS_CUSTOM_EMBED = False

# Couleur par défaut pour les embeds
THEME_COLOR = 0x3498db  # Bleu Discord par défaut
FOOTER = "Vax Bot - Système de hack"

class HackingSequence:
    def __init__(self, steps: List[dict]):
        self.steps = steps
        self.current_step = 0
    
    def get_step(self):
        if self.current_step >= len(self.steps):
            return None
        step = self.steps[self.current_step]
        self.current_step += 1
        return step

class Hack(commands.Cog):
    """Commande /hack — Système avancé de pénétration de sécurité."""

    def __init__(self, bot):
        self.bot = bot
        self.token = None  # Sera défini par setup()
        self.bot = bot
        self.hacking_sequences = {
            "standard": HackingSequence([
                {"emoji": "🔍", "action": "Scan initial du système", "time": 3.5, "success": 0.95},
                {"emoji": "🔓", "action": "Contournement du pare-feu", "time": 4.0, "success": 0.85},
                {"emoji": "🔑", "action": "Brute force des identifiants", "time": 5.0, "success": 0.75},
                {"emoji": "📡", "action": "Connexion au terminal distant", "time": 4.5, "success": 0.9},
                {"emoji": "💾", "action": "Extraction des données sensibles", "time": 6.0, "success": 0.8},
                {"emoji": "🧹", "action": "Effacement des traces", "time": 4.0, "success": 0.95},
                {"emoji": "🔍", "action": "Analyse des données récupérées", "time": 3.0, "success": 0.9}
            ])
        }
        self.hacker_aliases = [
            "Ghost", "Phantom", "Neo", "Cypher", "Zero", "Vex", "Nova", "Eclipse",
            "Spectre", "Raven", "Onyx", "Vortex", "Nyx", "Hex", "Cryptic", "Nebula",
            "Kraken", "Atlas", "Trinity", "Morbius", "Cobra", "Hydra", "Echo", "Glitch"
        ]
        
        # --- DONNÉES ÉTENDUES V2 ---
        
        # 1. Systèmes d'exploitation étendus
        self.operating_systems = [
            "Linux (Kali)", "Windows 11 Pro", "iOS 18.2", "macOS Ventura", "Android 15", 
            "Ubuntu 24.04 LTS", "FreeBSD 13.3", "ChromeOS", "Windows Server 2022"
        ]

        # 2. Corpus d'emails étendus
        self.emails_corpus = [
            "{username}.secrets@darkweb.mail",
            "{username}.onlyfans@proton.mail",
            "{username}.crypt0@tor.mail",
            "{username}_licorne_magique{rand}@hotmail.fr",
            "doudou.coeur_{year}@gmx.com",
            "admin_root_master{rand}@secure-corp.net",
            "{username}_gaming_pro{rand}@twitch.tv",
            "ceci.est.mon.vrai.mail{rand}@gmail.com",
            "ilovecatz{rand}@catmail.io",
            "compte_secondaire{rand}@mailinator.com",
            "achat_secret{rand}@darknet.onion",
            "fan_secret_kpop_{rand}@naver.com",
            "maitresse.damour{rand}@yahoo.fr",
            "contact.professionnel.faux{rand}@outlook.com",
            "le.roi.des.memes{rand}@troll.net"
        ]
        
        # 3. Corpus de fichiers étendus
        self.files_corpus = [
            "Photos/Selfies_Genants_ete_{year}",
            "Documents/Journal_Intime_2023.pdf",
            "Backup/Conversations_WhatsApp.enc",
            "Mes_Documents/Liste_de_souhaits_anniversaire.txt",
            "Telechargements/Recette_Gateau_Mamie.pdf",
            "Images/Memes_Interdits/",
            "Videos/Tutoriel_Maquillage_raté.mp4",
            "Configuration/Clés_SSH_Privées.bak",
            "Projets_Scolaires/Le_Poeme_Secret.doc",
            "Musique/Playlist_Chansons_Tristes.m3u",
            "Documents/CV_Faux_Pour_Job.pdf",
            "Images/Fond_d'écran_animé_kawaii.gif",
            "Finances/Relevés_Bancaires_2024.zip",
            "MesPapiers/Scan_Carte_ID.jpg",
            "Vidéos/Défis_TikTok_ridicules.mov",
            "Jeux/Sauvegarde_trichée_EldenRing.sav",
            "Confessions/Ma_vie_secrète_de_nuit.txt",
            "Travail/Projet_TopSecret_V5_Final.pptx"
        ]
        
        # 4. Corpus de mots de passe étendus
        self.passwords_corpus = [
            "Jaimelestartdusoleil{rand}",
            "{display_name}LePlusBeau{rand}",
            "JeSaisPasQuoiMettre{symbol}",
            "MotDePasseTropFacile{year}",
            "azerty{rand}123",
            "ilove{pet_name}42",
            "supermotdepasse{rand}!",
            "{username}{year}!",
            "Pa$$w0rdS3cur3",
            "MonChien{pet_name}{rand}",
            "LeSecretdesDieux{symbol}{year}",
            "MonMotDePasseSecret{dob_year}",
            "{pet_name}EstLeMeilleur{symbol}{rand}",
            "123456{dob_year}",
            "JeSuisUnGenie!{rand}",
            "{username}2025!"
        ]
        self.pet_names = ["Kiki", "Flocon", "Pelu", "Choupi", "Gribouille", "Shadow", "Muffin", "Diablo", "Sushi"]
        # ---------------------------------

    def _generate_ip(self):
        return f"{random.randint(10,255)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"

    def _generate_mac(self):
        return ":".join([f"{random.randint(0, 255):02x}" for _ in range(6)])

    def _generate_hacker_name(self):
        return f"{random.choice(self.hacker_aliases)}{random.randint(1, 999):03d}"

    def _generate_os(self):
        """Sélectionne un OS aléatoire parmi la liste."""
        return random.choice(self.operating_systems)

    @commands.hybrid_command(
        name="hack",
        description="Simule un hack sur un utilisateur spécifié"
    )
    @app_commands.describe(cible="La personne à hacker")
    async def hack(self, ctx: commands.Context, cible: discord.Member):
        """Simule un hack sur un utilisateur spécifié."""
        try:
            # 1. Accusé de réception (Utile pour les Slash Commands)
            await ctx.defer(ephemeral=False)
            
            # Vérification si la cible est un bot
            if cible.bot:
                error_msg = "❌ Impossible de hacker un bot !"
                if ctx.interaction:
                    await ctx.interaction.followup.send(error_msg, ephemeral=True)
                else:
                    await ctx.send(error_msg, reference=ctx.message)
                return
            
            # Vérification si la cible est le même utilisateur
            if cible == ctx.author:
                error_msg = "❌ Auto-hack détecté. Annulation pour raisons de sécurité."
                if ctx.interaction:
                    await ctx.interaction.followup.send(error_msg, ephemeral=True)
                else:
                    await ctx.send(error_msg, reference=ctx.message)
                return

            # Initialisation
            self.color = THEME_COLOR  # Utilisation de la constante de couleur
            hacker_name = self._generate_hacker_name()
            target_ip = self._generate_ip()
            target_os = self._generate_os()
            
            # Création de l'embed de démarrage
            if config_manager:
                embed = config_manager.get_formatted_embed(
                    guild=ctx.guild,
                    user=ctx.author,
                    bot=self.bot,
                    title="🔓 Initialisation du hack...",
                    description=f"Lancement de la séquence de piratage sur {cible.mention}...",
                    target_id=ctx.guild.id if ctx.guild else None
                )
            else:
                embed = discord.Embed(
                    title=f"🔓 Initialisation du hack...",
                    description=f"Lancement de la séquence de piratage sur {cible.mention}...",
                    color=THEME_COLOR  # Utilisation de la constante de couleur
                )
                embed.set_footer(text=FOOTER)  # Utilisation de la constante de pied de page
            
            # Envoi du message initial
            if ctx.interaction:
                message = await ctx.send(embed=embed)
            else:
                message = await ctx.send(embed=embed, reference=ctx.message, mention_author=True)
                
            await asyncio.sleep(1.5)
            
            # Création de l'embed de progression
            embed.clear_fields()
            embed.add_field(
                name="📡 CIBLE",
                value=f"```ansi\n\u001b[31m• Nom: {cible.display_name}\n\u001b[34m• ID: {cible.id}\n\u001b[35m• IP: {target_ip}\n\u001b[32m• OS: {target_os}\n\u001b[33m• MAC: {self._generate_mac()}```",
                inline=False
            )
            embed.add_field(
                name="⚙️ SYSTÈME",
                value="```diff\n+ Initialisation du protocole de piratage...\n+ Connexion sécurisée établie\n+ Chargement des modules...\n```",
                inline=False
            )
            
            # Envoi du message de progression
            if ctx.interaction:
                await message.edit(embed=embed)
            else:
                await message.edit(embed=embed)
                
            sequence = self.hacking_sequences.get("standard")
            if sequence is None or not hasattr(sequence, 'steps') or sequence.steps is None:
                error_msg = "❌ Erreur interne : la séquence de hack est introuvable. Merci de contacter un administrateur."
                if ctx.interaction:
                    await ctx.interaction.followup.send(error_msg, ephemeral=True)
                else:
                    await ctx.send(error_msg, reference=ctx.message)
                return
            total_steps = len(sequence.steps)
            
            for i, step in enumerate(sequence.steps, 1):
                progress_percent = min(100, int((i / total_steps) * 100))
                progress_bar_length = 30
                filled_length = int(progress_bar_length * i // total_steps)
                progress_bar = '█' * filled_length + '░' * (progress_bar_length - filled_length)
                
                # Définition des messages de statut
                status_msgs = [
                    "Analyse des vulnérabilités en cours...",
                    "Contournement des contre-mesures de sécurité...",
                    "Chiffrement des données en cours...",
                    "Élévation des privilèges...",
                    "Injection de charge utile...",
                    "Contournement de l'authentification à deux facteurs...",
                    "Accès root obtenu avec succès"
                ]
                
                # Détermination de la couleur de la barre de progression
                if progress_percent < 30:
                    color_code = '31'  # Rouge
                elif progress_percent < 70:
                    color_code = '33'  # Jaune
                else:
                    color_code = '32'  # Vert
                    
                # Mise à jour de la barre de progression
                embed.set_field_at(
                    1,
                    name=f"🚀 PROGRESSION: {progress_percent}%",
                    value=f"```ansi\n"
                          f"\033[1;{color_code}m{progress_bar}\033[0m\n"
                          f"\n"
                          f"\033[1;36m{step['emoji']} {step['action']}\033[0m\n"
                          f"\033[2m{random.choice(status_msgs)}\033[0m\n"
                          f"\n"
                          f"\033[1mÉtape {i} sur {total_steps}\033[0m"
                          f"```",
                    inline=False
                )
                
                # Ajout d'un message de trafic réseau aléatoire
                if random.random() < 0.3:
                    system_msgs = [
                        "[SYSTEM] Tentative de contre-mesure détectée...",
                        "[SECURITY] Pare-feu secondaire détecté...",
                        "[ENCRYPTION] Clé de chiffrement générée...",
                        "[NETWORK] Réacheminement du trafic..."
                    ]
                    if len(embed.fields) > 2 and embed.fields[2].name == "📡 TRAFIC RÉSEAU":
                        embed.remove_field(2)
                    embed.add_field(
                        name="📡 TRAFIC RÉSEAU",
                        value=f"```\n{random.choice(system_msgs)}\nIP Source: {self._generate_ip()}\nPort: {random.randint(1000, 9999)}\n```",
                        inline=False
                    )
                
                # Envoi du message de progression
                if ctx.interaction:
                    await message.edit(embed=embed)
                else:
                    await message.edit(embed=embed)
                    
                await asyncio.sleep(step['time'])
                
                if random.random() > step['success']:
                    embed.color = discord.Color.red()
                    embed.set_field_at(
                        1,
                        name="❌ ÉCHEC CRITIQUE",
                        value=f"```diff\n- ÉCHEC: {step['action']}\n- Raison: {random.choice(['Accès refusé', 'Déconnexion inattendue', 'Erreur de chiffrement', 'Détection par le système'])}\n- Tentative de récupération...\n```",
                        inline=False
                    )
                    # Envoi du message d'échec
                    if ctx.interaction:
                        await message.edit(embed=embed)
                    else:
                        await message.edit(embed=embed)
                        
                    await asyncio.sleep(1.5)
                    
                    embed.set_field_at(
                        1,
                        name="⚙️ SYSTÈME",
                        value=f"```diff\n+ Tentative de récupération...\n+ Réinitialisation des connexions...\n+ Réessai de l'opération...\n```",
                        inline=False
                    )
                    # Envoi du message de récupération
                    if ctx.interaction:
                        await message.edit(embed=embed)
                    else:
                        await message.edit(embed=embed)
                        
                    await asyncio.sleep(1.0)
            
            # Finalisation
            username = cible.name.lower().replace(' ', '_')
            display_name = cible.display_name
            current_year = datetime.datetime.now().year
            symbol = random.choice(['!', '?', '$', '#', '%', '&', '@'])
            pet_name = random.choice(self.pet_names)
            dob_year = random.randint(1980, 2005)  # Année de naissance aléatoire
            
            if config_manager:
                embed = config_manager.get_formatted_embed(
                    guild=ctx.guild,
                    user=ctx.author,
                    bot=self.bot,
                    title="✅ HACK RÉUSSI",
                    target_id=ctx.guild.id if ctx.guild else None
                )
            else:
                embed = discord.Embed(
                    title="✅ HACK RÉUSSI",
                    color=THEME_COLOR
                )
                embed.set_footer(text=FOOTER)
            
            # Définir la description avec le message de piratage
            embed.description = f"{cible.mention}, tu as été hacké par **{hacker_name}** !"
            symbol = random.choice(['!', '?', '$', '#', '%', '&', '@'])
            pet_name = random.choice(self.pet_names)
            dob_year = random.randint(1980, 2005) # Année de naissance aléatoire
            
            # Formatage des listes de données
            emails_list = [
                e.format(username=username, year=current_year, rand=random.randint(100, 999))
                for e in self.emails_corpus
            ]
            files_list = [
                f.format(year=current_year, rand=random.randint(1, 99))
                for f in self.files_corpus
            ]
            passwords_list = [
                p.format(display_name=display_name, username=username, year=current_year, rand=random.randint(1, 999), symbol=symbol, pet_name=pet_name, dob_year=dob_year)
                for p in self.passwords_corpus
            ]
            
            # Sélection de 6 éléments de chaque type
            fake_emails = random.sample(emails_list, k=min(6, len(emails_list)))
            fake_files = random.sample(files_list, k=min(6, len(files_list)))
            fake_passwords = random.sample(passwords_list, k=min(6, len(passwords_list)))
            
            # Génération du rapport détaillé
            report = [
                "\033[1;36m📊 RAPPORT D'ACCÈS FINAL\033[0m",
                "\033[1;37m" + "═" * 45 + "\033[0m",
                f"\033[1;35m•\033[0m \033[1;33mCible:\033[0m \033[1;37m{cible.display_name}\033[0m (\033[1;32m{cible.id}\033[0m)",
                f"\033[1;35m•\033[0m \033[1;33mSystème:\033[0m \033[1;36m{target_os}\033[0m",
                f"\033[1;35m•\033[0m \033[1;33mIP:\033[0m \033[1;36m192.168.1.{random.randint(1, 255)}\033[0m",
                "",
                "\033[1;34m📧 ADRESSES EMAIL INTERCEPTÉES\033[0m"
            ]
            
            for email in fake_emails:
                report.append(f"\033[1;35m•\033[0m \033[1;36m{email}\033[0m")
            
            report.extend([
                "",
                "\033[1;34m📂 FICHIERS SENSIBLES EXFILTRÉS\033[0m"
            ])
            
            for file in fake_files:
                report.append(f"\033[1;35m•\033[0m \033[1;33m{file}\033[0m")
            
            report.extend([
                "",
                "\033[1;34m🔑 MOTS DE PASSE/CLÉS RÉCUPÉRÉS\033[0m"
            ])
            
            for pwd in fake_passwords:
                report.append(f"\033[1;35m•\033[0m \033[1;31m{pwd}\033[0m")
            
            report.extend([
                "",
                "\033[1;31m🔒 NETTOYAGE DES TRACES (Protocole Ghost)\033[0m",
                "\033[1;35m•\033[0m \033[1;32mSuppression de l'historique de navigation\033[0m",
                "\033[1;35m•\033[0m \033[1;32mDésactivation des journaux système\033[0m",
                "\033[1;35m•\033[0m \033[1;32mBrouillage des adresses IP\033[0m",
                "\033[1;35m•\033[0m \033[1;32mNettoyage des métadonnées\033[0m"
            ])
            embed.clear_fields()
            embed.description = "```ansi\n" + "\n".join(report) + "\n\n\033[1;32m✅ ACCÈS COMPLET ET PERMANENT OBTENU\n[VAX] Terminé: Système compromis, aucune trace\033[0m\n```"

            # Envoi du rapport final
            if ctx.interaction:
                await message.edit(embed=embed)
            else:
                await message.edit(embed=embed)

        except Exception as e:
            await ctx.send(f"Erreur : {e}", ephemeral=True)
            traceback.print_exc()

    @commands.Cog.listener()
    async def on_ready(self):
        if not getattr(self.bot, "_hack_synced", False):
            try:
                await self.bot.tree.sync()
                self.bot._hack_synced = True
            except:
                pass

async def setup(bot: commands.Bot):
    if bot.get_command("hack"):
        bot.remove_command("hack")
    await bot.add_cog(Hack(bot))