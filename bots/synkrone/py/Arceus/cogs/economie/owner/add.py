import discord
from discord.ext import commands

# N'oublie pas d'adapter l'import selon ton architecture de dossiers
from cogs.economie.utils import EconomyService


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.eco = EconomyService(bot)

    @commands.command(name="add", description="Ajoute ou retire des Pokédollars (Owner only).")
    @commands.is_owner() # Sécurité : seul le propriétaire du bot peut exécuter cette commande
    async def add_money(self, ctx: commands.Context, arg1: str, arg2: str = None):
        """
        Utilisation :
        !add <montant> (Ajoute à soi-même)
        !add <id> <montant> (Ajoute à un joueur spécifique)
        Montants valides : 100, +100, -100
        """
        
        # 1. Détermination de l'ID cible et du montant à partir des arguments
        if arg2 is None:
            # Si un seul argument est fourni, c'est le montant, la cible est l'auteur
            target_id = ctx.author.id
            amount_str = arg1
        else:
            # Si deux arguments sont fournis, le premier est l'ID, le second le montant
            try:
                target_id = int(arg1)
            except ValueError:
                await ctx.send("❌ **Erreur :** L'ID de l'utilisateur doit être un nombre valide.")
                return
            amount_str = arg2

        # 2. Conversion du montant (la fonction int() gère automatiquement "+100" et "-100")
        try:
            amount = int(amount_str)
        except ValueError:
            await ctx.send("❌ **Erreur :** Le montant doit être un nombre valide (ex: 100, +100, -100).")
            return

        # 3. S'assurer que l'utilisateur existe dans la base de données
        self.eco.ensure_user(target_id)

        # 4. Application du changement (MAX(0, ...) permet de ne pas avoir de solde négatif)
        with self.eco._get_conn() as conn:
            conn.execute(
                "UPDATE users SET balance = MAX(0, balance + ?) WHERE user_id = ?",
                (amount, target_id)
            )
            
            # Récupérer le nouveau solde pour l'afficher
            row = conn.execute("SELECT balance FROM users WHERE user_id = ?", (target_id,)).fetchone()
            new_balance = row["balance"]

        # 5. Création du message de réponse
        action = "ajoutés à" if amount >= 0 else "retirés de"
        abs_amount = abs(amount)
        
        # Si c'est l'auteur, on dit "toi-même", sinon on mentionne le joueur
        user_mention = f"<@{target_id}>" if target_id != ctx.author.id else "ton compte"

        await ctx.send(f"✅ **{abs_amount}** Pokédollars ont été {action} {user_mention}. (Nouveau solde : **{new_balance}**)")


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))