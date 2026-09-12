import discord
from discord.ext import commands
import json
import os
from datetime import datetime

class Echange(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.user_data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'interserver')
        
    @commands.hybrid_command(name='echange')
    async def echange(self, ctx, action: str = None, target_user: discord.User = None, card_id: str = None, amount: int = 1):
        """Gère les échanges de cartes entre utilisateurs"""
        
        if action is None:
            embed = discord.Embed(
                title="🔄 Système d'Échange",
                description="Commandes disponibles pour les échanges de cartes",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="📋 Commandes",
                value=(
                    "`.echange propose <utilisateur> <carte_id> [quantité]` - Proposer un échange\n"
                    "`.echange accept <utilisateur>` - Accepter un échange proposé\n"
                    "`.echange refuse <utilisateur>` - Refuser un échange proposé\n"
                    "`.echange annuler` - Annuler votre proposition en cours\n"
                    "`.echange liste` - Voir les échanges en attente"
                ),
                inline=False
            )
            embed.add_field(
                name="💡 Exemples",
                value=(
                    "`.echange propose @user ABC123 2` - Proposer 2 cartes ABC123\n"
                    "`.echange accept @user` - Accepter l'échange de @user\n"
                    "`.echange liste` - Voir les propositions en attente"
                ),
                inline=False
            )
            embed.set_footer(text="Utilisez `.echange` suivi d'une action pour commencer")
            await ctx.send(embed=embed)
            return
        
        user_id_str = str(ctx.author.id)
        user_file = os.path.join(self.user_data_path, f"{user_id_str}.json")
        
        # Vérifier si l'utilisateur a un profil
        if not os.path.exists(user_file):
            await ctx.send("❌ Vous devez avoir un profil pour faire des échanges !")
            return
        
        # Charger les données utilisateur
        try:
            with open(user_file, 'r', encoding='utf-8') as f:
                user_data = json.load(f)
        except:
            await ctx.send("❌ Erreur lors du chargement de vos données.")
            return
        
        if action.lower() == "propose":
            await self.handle_propose(ctx, user_data, target_user, card_id, amount)
        elif action.lower() == "accept":
            await self.handle_accept(ctx, user_data, target_user)
        elif action.lower() == "refuse":
            await self.handle_refuse(ctx, user_data, target_user)
        elif action.lower() == "annuler":
            await self.handle_annuler(ctx, user_data)
        elif action.lower() == "liste":
            await self.handle_liste(ctx, user_data)
        else:
            await ctx.send(f"❌ Action `{action}` non reconnue. Utilisez `.echange` pour voir les commandes.")
    
    async def handle_propose(self, ctx, user_data, target_user, card_id, amount):
        """Gère la proposition d'échange"""
        if not target_user:
            await ctx.send("❌ Vous devez mentionner un utilisateur avec qui échanger.")
            return
        
        if target_user.id == ctx.author.id:
            await ctx.send("❌ Vous ne pouvez pas échanger avec vous-même.")
            return
        
        if not card_id:
            await ctx.send("❌ Vous devez spécifier l'ID de la carte à échanger.")
            return
        
        if amount <= 0:
            await ctx.send("❌ La quantité doit être positive.")
            return
        
        # Vérifier si l'utilisateur a les cartes
        collection = user_data.get('collection', {})
        if card_id not in collection or collection[card_id] < amount:
            await ctx.send(f"❌ Vous n'avez pas assez de cartes `{card_id}` (vous en avez {collection.get(card_id, 0)}).")
            return
        
        # Vérifier si l'utilisateur cible a un profil
        target_file = os.path.join(self.user_data_path, f"{target_user.id}.json")
        if not os.path.exists(target_file):
            await ctx.send(f"❌ {target_user.mention} n'a pas de profil.")
            return
        
        # Créer la proposition d'échange
        if 'echanges_proposes' not in user_data:
            user_data['echanges_proposes'] = {}
        
        if 'echanges_recus' not in user_data:
            user_data['echanges_recus'] = {}
        
        # Ajouter la proposition
        propose_key = f"{target_user.id}"
        user_data['echanges_proposes'][propose_key] = {
            'target_id': target_user.id,
            'target_name': target_user.display_name,
            'card_id': card_id,
            'amount': amount,
            'timestamp': datetime.now().isoformat(),
            'status': 'en_attente'
        }
        
        # Sauvegarder les données
        await self.save_user_data(ctx.author.id, user_data)
        
        # Notifier l'utilisateur cible
        try:
            embed = discord.Embed(
                title="🔄 Proposition d'Échange",
                description=f"**{ctx.author.mention}** vous propose un échange !",
                color=discord.Color.gold()
            )
            embed.add_field(
                name="📦 Carte proposée",
                value=f"**{amount}x** carte `{card_id}`",
                inline=True
            )
            embed.add_field(
                name="👤 Proposé par",
                value=ctx.author.mention,
                inline=True
            )
            embed.add_field(
                name="⏰ Date",
                value=datetime.now().strftime("%d/%m/%Y %H:%M"),
                inline=False
            )
            embed.add_field(
                name="🎯 Actions",
                value="Utilisez `.echange accept @proposant` pour accepter\nUtilisez `.echange refuse @proposant` pour refuser",
                inline=False
            )
            embed.set_footer(text="La proposition expirera après 24h")
            
            await target_user.send(embed=embed)
            
            # Confirmation pour le proposant
            await ctx.send(f"✅ Proposition d'échange envoyée à {target_user.mention} !")
            
        except discord.Forbidden:
            await ctx.send(f"✅ Proposition enregistrée, mais {target_user.mention} a désactivé les MPs.")
    
    async def handle_accept(self, ctx, user_data, target_user):
        """Gère l'acceptation d'échange"""
        if not target_user:
            await ctx.send("❌ Vous devez mentionner l'utilisateur qui a proposé l'échange.")
            return
        
        # Vérifier s'il y a une proposition en attente
        if 'echanges_recus' not in user_data:
            await ctx.send("❌ Vous n'avez aucune proposition d'échange en attente.")
            return
        
        propose_key = str(target_user.id)
        if propose_key not in user_data['echanges_recus']:
            await ctx.send(f"❌ Aucune proposition de {target_user.mention} en attente.")
            return
        
        proposition = user_data['echanges_recus'][propose_key]
        
        # Vérifier si la proposition est toujours valide
        if proposition.get('status') != 'en_attente':
            await ctx.send("❌ Cette proposition n'est plus valide.")
            return
        
        # Charger les données du proposant
        proposer_file = os.path.join(self.user_data_path, f"{target_user.id}.json")
        try:
            with open(proposer_file, 'r', encoding='utf-8') as f:
                proposer_data = json.load(f)
        except:
            await ctx.send("❌ Erreur lors du chargement des données du proposant.")
            return
        
        # Vérifier si le proposant a toujours les cartes
        card_id = proposition['card_id']
        amount = proposition['amount']
        proposer_collection = proposer_data.get('collection', {})
        
        if card_id not in proposer_collection or proposer_collection[card_id] < amount:
            await ctx.send("❌ Le proposant n'a plus les cartes nécessaires.")
            return
        
        # Effectuer l'échange
        # Retirer les cartes du proposant
        proposer_collection[card_id] -= amount
        if proposer_collection[card_id] == 0:
            del proposer_collection[card_id]
        proposer_data['collection'] = proposer_collection
        
        # Ajouter les cartes à l'utilisateur
        user_collection = user_data.get('collection', {})
        user_collection[card_id] = user_collection.get(card_id, 0) + amount
        user_data['collection'] = user_collection
        
        # Mettre à jour le statut
        proposition['status'] = 'accepte'
        proposition['accepted_at'] = datetime.now().isoformat()
        
        # Sauvegarder les deux utilisateurs
        await self.save_user_data(ctx.author.id, user_data)
        await self.save_user_data(target_user.id, proposer_data)
        
        # Confirmation
        embed = discord.Embed(
            title="✅ Échange Accepté !",
            description=f"Échange réussi entre {ctx.author.mention} et {target_user.mention}",
            color=discord.Color.green()
        )
        embed.add_field(
            name="📦 Carte échangée",
            value=f"**{amount}x** carte `{card_id}`",
            inline=True
        )
        embed.add_field(
            name="🔄 Transfert",
            value=f"{target_user.mention} → {ctx.author.mention}",
            inline=True
        )
        embed.set_footer(text="Échange complété avec succès !")
        
        await ctx.send(embed=embed)
        
        # Notifier le proposant
        try:
            notif_embed = discord.Embed(
                title="✅ Votre échange a été accepté !",
                description=f"{ctx.author.mention} a accepté votre proposition d'échange",
                color=discord.Color.green()
            )
            notif_embed.add_field(
                name="📦 Carte échangée",
                value=f"**{amount}x** carte `{card_id}`",
                inline=True
            )
            await target_user.send(notif_embed)
        except discord.Forbidden:
            pass  # Le proposant a désactivé les MPs
    
    async def handle_refuse(self, ctx, user_data, target_user):
        """Gère le refus d'échange"""
        if not target_user:
            await ctx.send("❌ Vous devez mentionner l'utilisateur qui a proposé l'échange.")
            return
        
        if 'echanges_recus' not in user_data:
            await ctx.send("❌ Vous n'avez aucune proposition d'échange en attente.")
            return
        
        propose_key = str(target_user.id)
        if propose_key not in user_data['echanges_recus']:
            await ctx.send(f"❌ Aucune proposition de {target_user.mention} en attente.")
            return
        
        proposition = user_data['echanges_recus'][propose_key]
        proposition['status'] = 'refuse'
        proposition['refused_at'] = datetime.now().isoformat()
        
        # Sauvegarder
        await self.save_user_data(ctx.author.id, user_data)
        
        await ctx.send(f"❌ Proposition de {target_user.mention} refusée.")
        
        # Notifier le proposant
        try:
            embed = discord.Embed(
                title="❌ Votre échange a été refusé",
                description=f"{ctx.author.mention} a refusé votre proposition d'échange",
                color=discord.Color.red()
            )
            await target_user.send(embed)
        except discord.Forbidden:
            pass
    
    async def handle_annuler(self, ctx, user_data):
        """Gère l'annulation de proposition"""
        if 'echanges_proposes' not in user_data or not user_data['echanges_proposes']:
            await ctx.send("❌ Vous n'avez aucune proposition d'échange en cours.")
            return
        
        # Supprimer toutes les propositions
        user_data['echanges_proposes'] = {}
        await self.save_user_data(ctx.author.id, user_data)
        
        await ctx.send("✅ Toutes vos propositions d'échange ont été annulées.")
    
    async def handle_liste(self, ctx, user_data):
        """Affiche la liste des échanges en attente"""
        embed = discord.Embed(
            title="🔄 Vos Échanges",
            color=discord.Color.blue()
        )
        
        # Propositions envoyées
        if 'echanges_proposes' in user_data and user_data['echanges_proposes']:
            proposes_text = ""
            for key, prop in user_data['echanges_proposes'].items():
                if prop['status'] == 'en_attente':
                    proposes_text += f"📦 **{prop['amount']}x** `{prop['card_id']}` → **{prop['target_name']}**\n"
            
            if proposes_text:
                embed.add_field(
                    name="📤 Propositions envoyées",
                    value=proposes_text,
                    inline=False
                )
        
        # Propositions reçues
        if 'echanges_recus' in user_data and user_data['echanges_recus']:
            recus_text = ""
            for key, prop in user_data['echanges_recus'].items():
                if prop['status'] == 'en_attente':
                    recus_text += f"📦 **{prop['amount']}x** `{prop['card_id']}` ← **{prop['target_name']}**\n"
            
            if recus_text:
                embed.add_field(
                    name="📥 Propositions reçues",
                    value=recus_text,
                    inline=False
                )
        
        if not embed.fields:
            embed.description = "Aucun échange en attente."
        
        embed.set_footer(text="Utilisez `.echange` pour voir les commandes disponibles")
        await ctx.send(embed=embed)
    
    async def save_user_data(self, user_id, user_data):
        """Sauvegarde les données utilisateur"""
        user_file = os.path.join(self.user_data_path, f"{user_id}.json")
        try:
            with open(user_file, 'w', encoding='utf-8') as f:
                json.dump(user_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Erreur sauvegarde utilisateur {user_id}: {e}")

async def setup(bot):
    await bot.add_cog(Echange(bot))
