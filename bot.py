"""
	Discord bot for a french game called loups-garous

	created by Maximino, student in computer science
"""

###### Discord API ######
import discord
from discord.ext import commands
from discord.utils import get
######

import asyncio

###### For Audio integration ######
import nacl
import ffmpeg
######

import random

import game

class LGBot(commands.Bot):
	def __init__(self, intents, help_command):
		super().__init__(command_prefix="$", intents=intents, help_command=help_command)
		self.remove_command('help')

		self.game = None

		self.step = 0

		# dict of current cards used in the game, 
		# with roles as keys and number of members with this role as value
		# ex : {"loup": 2}
		self.cards = {}

		self.channel_source = None # Channel from where the bot was called
		self.loups_channel = None # Channel for role <loup>
		self.ctx_channel = None # Channel to send messages with the bot
		self.chans = [] # List of chans created in the game

		@self.command(name="start")
		async def _start(ctx: discord.Client):
			"""
				Commence une partie de loups-garous, il faut au préalable être dans un channel vocal
				et avoir au moins 6 joueurs dans ce channel.
			"""
			if hasattr(ctx.author.voice, 'channel'):
				destination = ctx.author.voice.channel

				try:
					await destination.connect()
				except:
					await ctx.voice_client.disconnect()
					return

				self._play_audio(ctx, ".env/Include/sounds/wolf.mp3")

				party_members = [] # list of actual members of the party (without the bot)
				for member in destination.members:
					if member.name != "LG": # LG is the name of the bot
						party_members.append(member)
				n_members = len(party_members)

				#if n_members < 6 or n_members > 10:
				#	return await ctx.send("Il faut au moins 6 joueurs pour lancer une partie, et au max 10 joueurs")

				self.game = game.Game()
				self.game.n_members = n_members
				self.game.members = party_members
				self.channel_source = destination

				await self._fill_cards(ctx, n_members)

				if sum(self.cards.values()) != n_members:
					await ctx.send("Le nombre de cartes n'est pas égal au "\
						"nombre de joueurs... ({} joueur(s) et {} cartes)".format(n_members, sum(self.cards.values())))
					return

				await ctx.send("La Partie commence ! Regardez vos "\
							"messages privés pour connaître votre rôle")
				msg = ""
				for role, nb in self.cards.items():
					if nb != 0:
						msg += role + " : " + str(nb) + "\n"
				await ctx.send("Configuration de la partie : \n" + msg)

				self._shuffle(party_members)

				await self._send_roles(self.game.roles)

				# We can start the game
				await self._start_game(ctx)
			else:
				return await ctx.send("Il faut rejoindre un salon vocal avant de m'appeler")

		@self.command(name="stop")
		async def _stop(ctx: discord.Client):
			"""
				Disconnect the bot from a voice channel, and delete all created channels
			"""
			if not ctx.voice_client or not ctx.voice_client.is_connected():
				return await ctx.send("Je ne suis connecté à aucun salon...")

			self.cards = {}
			if self.loups_channel != None:
				await self.loups_channel.delete()

			if self.ctx_channel != None:
				await self.ctx_channel.delete()

			for chan in self.chans:
				await chan.delete()
			self.chans = []
			self.game = game.Game()
			self.step = 0

			await ctx.voice_client.disconnect()

		@self.command(name="help")
		async def _help(ctx: discord.Client):
			msg = "Liste des commandes ($):\n\n      - start : Lance une partie de loups-garous"\
					"\n      - stop : Déconnecte le bot d'un channel\n      - help : Affiche ce message"\
					"\n      - roles : Affiche la liste des rôles possibles"
			embed = discord.Embed(name="Maître du jeu", title="Aide",
							description=msg, colour=discord.Colour.red())
			return await ctx.send(embed=embed)

		@self.command(name="roles")
		async def _roles(ctx: discord.Client):
			msg = "Voici la liste des rôles disponibles :\n\n      - Loup-garou\n      - Villageois\n      - Sorcière"\
					"\n      - Petite fille\n      - Cupidon\n      - Voyante\n      - Chasseur"
			embed = discord.Embed(name="Maitre du jeu", title="Roles",
				description=msg, colour=discord.Colour.red())
			return await ctx.send(embed=embed)

	async def _start_game(self, ctx: discord.Client):

		cat = self.find_category(ctx, "Loups-garous")
		guild = ctx.message.guild

		# Creating a text channel to send messages
		self.ctx_channel = await guild.create_text_channel('Village', category=cat)

		while not self.game.finished():
			# Every member goes on a private channel
			await self.dispatch_members(ctx)

			if self.step == 0 and "cupidon" in self.game.roles.values():
				await self.cupidon(ctx)
			if "voyante" in self.game.roles.values():
				await self.voyante(ctx)
			await self.loup(ctx)
			if "sorciere" in self.game.roles.values():
				await self.sorciere(ctx)
			else:
				self.game.add_member_to_victims(self.game.current_victim)

			await self._bring_back_members(ctx)
			await self.recap(ctx)

			# If theres only one player or less, the game is finished
			if self.game.n_members <= 1:
				if self.game.n_members == 0:
					await self._send_context("La partie est finie !\n Personne n'a gagné... C'etait un bon bain de sang", "FIN")
				elif "loup" in self.game.roles.values():
					await self._send_context("La partie est finie !\n Les loups-garous ont gagné", "FIN")
				else:
					await self._send_context("La partie est finie !\n Les villageois ont gagné", "FIN")
				for member in ctx.author.voice.channel.members:
					await member.edit(mute=False)
				return

			await self.vote(ctx)

			self.game.clean_daily_victims()
			self.game.current_victim = None

		if "loup" in self.game.roles.values():
			await self._send_context("La partie est finie !\n Les loups-garous ont gagné", "FIN")
		else:
			await self._send_context("La partie est finie !\n Les villageois ont gagné", "FIN")
		for member in ctx.author.voice.channel.members:
			await member.edit(mute=False)

	async def _send_dm(self, member: discord.Member, msg: str, title: str, file=None):
		dm = await member.create_dm()
		embed = discord.Embed(name="Maitre du jeu", title=title,
						description=msg,colour=discord.Colour.red())
		return await dm.send(embed=embed, file=file)

	async def _send_context(self, msg: str, title=None):
		embed = discord.Embed(name="Maitre du jeu", title=title,
							description=msg, colour=discord.Colour.red())
		return await self.ctx_channel.send(embed=embed)

	async def _send_roles(self, roles: list):
		for member in roles.keys():
			role = roles[member]
			with open(".env/Include/images/{}.jpg".format(role), "rb") as fh:
				f = discord.File(
					fh, filename="{}.jpg".format(role))
			await self._send_dm(member, "CHUUUUUT... Je viens de déposer ta carte sur la table"\
					"\nVeille à ce que personne ne la voie...", "Carte", f)

	async def _fill_cards(self, ctx: discord.Client, n_members: int):

		emojis = ["0️⃣","1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]

		def check(reaction, user):
			return str(reaction.emoji) in emojis and user == ctx.message.author

		for card in self.game.cards:
			embed = discord.Embed(name="Maitre du jeu", title="Config",
				description=f"Combien de roles <{card}> voulez-vous ?",colour=discord.Colour.red())
			message = await ctx.send(embed=embed)

			if card in ["cupidon", "petite-fille", "voyante", "sorciere", "chasseur"]:
				await message.add_reaction(emojis[0])
				await message.add_reaction(emojis[1])
			elif card == "loup":
				for i in range(n_members + 1): # TODO : In release, start i with 2
					await message.add_reaction(emojis[i])
			else:
				for i in range(n_members + 1):
					await message.add_reaction(emojis[i])

			try:
				reaction, user = await self.wait_for("reaction_add", check=check, timeout=120)
			except asyncio.TimeoutError:
				await message.delete()
				await ctx.send("Timed out")
				return

			index = emojis.index(reaction.emoji)
			self.cards[card] = index

			await message.delete()

	def _shuffle(self, members: list):
		d = {}
		tmp_members = members[:]
		for key in self.cards.keys():
			for i in range(self.cards[key]):
				m = random.choice(tmp_members)
				tmp_members.remove(m)
				d[m] = key
		self.game.roles = d

	def _play_audio(self, ctx: discord.Client, source):
		ctx.voice_client.play(discord.FFmpegOpusAudio(
			executable=".env/Lib/site-packages/ffmpeg/bin/ffmpeg.exe", source=source))

	async def dispatch_members(self, ctx: discord.Client):
		"""
			Creates a new voice channel only for one member, and move each member to his channel
			Pre-condition : A category loups-garous is created, otherwise it is created
		"""
		cat = self.find_category(ctx, "Loups-garous")
		guild = ctx.message.guild
		if cat == None:
			await guild.create_category_channel('Loups-garous')
			cat = self.find_category(ctx, "Loups-garous")
		for member in self.game.members:
			overwrites = {
				guild.default_role: discord.PermissionOverwrite(read_messages=False),
				member: discord.PermissionOverwrite(read_messages=True),
			}
			chan = await guild.create_voice_channel(member.name, category=cat, overwrites=overwrites)
			await member.move_to(chan, reason="Les villageois se rendorment...")
			self.chans.append(chan)

	async def _bring_back_members(self, ctx: discord.Client):
		"""
			Bring back all game players in the source channel
		"""
		for member in self.game.members:
			await member.move_to(self.channel_source, reason="Les villageois se réveillent...")

	def find_category(self, ctx: discord.Client, name):
		for category in ctx.message.guild.categories:
			if category.name == name:
				return category
		return None

	async def _kill(self, member):
		""" 
			Removes a member from the game by calling the remove_member method from the Game object,
			If this member has the role <chasseur>, he can kill someone before dying
		"""
		# We test if the member is a hunter (chasseur)
		if self.game.roles[member] == "chasseur":
			msg = ""
			i = 0
			member_index = 0
			for m in self.game.members:
				if m == member:
					member_index = i
					continue
				msg += str(i) + ". " + m.name + "\n"
				i += 1
	
			emojis = ["0️⃣","1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]

			message = await self._send_context(f"{member.name}, étant chasseur, peut tuer quelqu'un avant de mourir !\
				\nChoisis ta victime parmi cette liste:\n" + msg,
				"Dernière chance")

			for i in range(self.game.n_members - 1):
				await message.add_reaction(emojis[i])

			def check(reaction, user):
				return str(reaction.emoji) in emojis and user.name == member.name

			reaction, user = await self.wait_for("reaction_add", check=check)

			index = emojis.index(reaction.emoji)
			if index >= member_index:
				index += 1
			target = self.game.members[index]

			await self._send_context(f"{target.name} est mort(e), cette personne était... {self.game.roles[target]} !", "Journée")

			if target in self.game.couple:
				self.game.couple.remove(target)
				couple = self.game.couple[0]
				await self._send_context(f"{target.name} était en couple avec {couple}...\n "\
					f"{couple} avec le role {self.game.roles[couple]} meurt donc de chagrin", "Journée")
				self.game.remove_member(couple)
				await couple.edit(mute=True)

			self.game.remove_member(target)
			await target.edit(mute=True)

		self.game.remove_member(member)
		await member.edit(mute=True)

######################################################################
################									##################
################ Methods for each role in the game. ##################
################									##################
######################################################################

	async def cupidon(self, ctx: discord.Client):
		await self._send_context("Cupidon, choisis deux personnes amoureuses...", f"Tour n°{self.step}")
		msg = "Salut Cupidon, choisis les deux amoureux de la partie : \n\t"
		cupidon = None
		i = 0
		for member in self.game.members:
			if self.game.roles[member] == "cupidon":
				cupidon = member
			msg = msg + str(i) + ". " + member.name + "\n\t"
			i += 1
	
		emojis = ["0️⃣","1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
		message = await self._send_dm(cupidon, msg, "A toi de choisir")

		def check(reaction, user):
			return str(reaction.emoji) in emojis and user.name == cupidon.name

		for i in range(self.game.n_members):
			await message.add_reaction(emojis[i])

		reaction, user = await self.wait_for("reaction_add", check=check)

		index1 = emojis.index(reaction.emoji)
		couple1 = self.game.members[index1]

		reaction, user = await self.wait_for("reaction_add", check=check)

		index2 = emojis.index(reaction.emoji)
		couple2 = self.game.members[index2]

		if couple1 != couple2:
			self.game.couple = [couple1, couple2]
			await self._send_dm(couple1, f"Coucou, tu es maintenant en couple avec {couple2.name} ! Felicitations", "Cupidon")
			await self._send_dm(couple2, f"Coucou, tu es maintenant en couple avec {couple1.name} ! Felicitations", "Cupidon")

	async def voyante(self, ctx: discord.Client):
		await self._send_context("La voyante choisit quelqu'un à espionner...", f"Tour n°{self.step}")
		msg = "Tu as le choix d'espionner quelqu'un ! Choisis parmi cette liste : \n\t"

		voyante = None
		i = 0
		v_index = 0 # voyante index
		for member in self.game.members:
			if self.game.roles[member] == "voyante":
				voyante = member
				v_index = i
			else:
				msg = msg + str(i) + ". " + member.name + "\n"
				i += 1
	
		emojis = ["0️⃣","1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣"]
		message = await self._send_dm(voyante, msg, "A toi de choisir")

		for i in range(self.game.n_members - 1):
			await message.add_reaction(emojis[i])

		def check(reaction, user):
			return str(reaction.emoji) in emojis and user.name == voyante.name

		reaction, user = await self.wait_for("reaction_add", check=check)

		index = emojis.index(reaction.emoji)
		if index >= v_index:
			index += 1
		target = self.game.members[index]

		role_target = self.game.roles[target]

		await self._send_dm(voyante, f"{target.name} est...\n-----> {role_target} <----- !", f"Rôle de {target.name}")

	async def loup(self, ctx: discord.Client):
		await self._send_context("Les loups-garous se réveillent !\n" \
			"C'est à leur tour de choisir une victime", f"Tour n°{self.step}")

		loups = [member for member in self.game.members if self.game.roles[member] == "loup"]

		# Creation of voice channel and move all <loup> roles in there
		cat = self.find_category(ctx, "Loups-garous")
		guild = ctx.message.guild

		# The role <petite-fille> is able to see which players are <loup>
		petite_fille = None
		if "petite-fille" in self.game.roles.values():
			for member in self.game.members:
				if self.game.roles[member] == "petite-fille":
					petite_fille = member

		if petite_fille != None:
			# if theres a petite-fille in the game, we give her permissions to see wolves channel
			overwrites = {
				guild.default_role: discord.PermissionOverwrite(read_messages=False),
				petite_fille: discord.PermissionOverwrite(read_messages=True)
			}
		else:
			overwrites = {
				guild.default_role: discord.PermissionOverwrite(read_messages=False)
			}

		chan = await guild.create_voice_channel("loups", category=cat, overwrites=overwrites)
		self.chans.append(chan)
		for loup in loups:
			await loup.move_to(chan, reason="Les loups se reveillent...")

		self.loups_channel = await guild.create_text_channel('salon_loups', overwrites=overwrites, category=cat)

		for loup in loups:
			await self.loups_channel.set_permissions(loup, read_messages=True)

		i = 0

		msg = "Loups-garous à vous de jouer ! Choisissez votre victime parmi cette liste : \n\t"
		for member in self.game.members:
			msg = msg + str(i) + ". " + member.name + "\n\t"
			i += 1
		embed = discord.Embed(name="Maitre du jeu", title="A vous de choisir",
						description=msg,colour=discord.Colour.red())
		message = await self.loups_channel.send(embed=embed)

		emojis = ["0️⃣","1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣"]

		voted = []
		votes = {}

		def check(reaction, user):
			if str(reaction.emoji) in emojis and user in loups and user.name not in voted:
				voted.append(loup.name)

				index = emojis.index(reaction.emoji)
				if self.game.members[index] not in votes.keys():
					votes[self.game.members[index]] = 1
				else:
					votes[self.game.members[index]] += 1

				if len(loups) == len(voted):
					return True

			return False

		for i in range(self.game.n_members):
			await message.add_reaction(emojis[i])

		reaction, user = await self.wait_for("reaction_add", check=check)

		maxvote = 0
		maxvote2 = 0

		for key, nb_votes in votes.items():
			if nb_votes > maxvote:
				victim = key
				maxvote2 = maxvote
				maxvote = nb_votes
			elif nb_votes > maxvote2:
				maxvote2 = nb_votes

		for loup in loups:
			for chan in self.chans:
				if chan.name == loup.name:
					await member.move_to(chan)

		if maxvote != maxvote2:
			self.game.current_victim = victim

	async def sorciere(self, ctx: discord.Client):
		sorciere = None
		i = 0
		s_index = 0
		for member in self.game.members:
			if self.game.roles[member] == "sorciere":
				sorciere = member
				s_index = i
			i += 1

		await self._send_context("La sorcière se réveille !\n", f"Tour n°{self.step}")

		if self.game.current_victim != None:
			msg = f"C'est ton tour sorcière, les loups ont décidé de manger {self.game.current_victim}\n"
		else:
			msg = "C'est ton tour sorcière, les loups ne se sont pas mis d'accord pour manger quelqu'un.\n"
		msg = msg + f"Il te reste {self.game.heal_potion} élixir de guérison et {self.game.poison_potion} élixir de poison"\
				", Fais ton choix :\n        0. Ne rien faire\n        1. Elixir de poison\n        2. Elixir de guérison"

		message = await self._send_dm(sorciere, msg, "Sorcière")

		emojis = ["0️⃣","1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣"]

		for i in range(3):
			await message.add_reaction(emojis[i])

		def check(reaction, user):
			if emojis.index(reaction.emoji) == 1 and self.game.poison_potion == 0 and self.game.current_victim != None:
				return False
			if emojis.index(reaction.emoji) == 2 and self.game.heal_potion == 0:
				return False
			return str(reaction.emoji) in emojis and user.name == sorciere.name

		reaction, user = await self.wait_for("reaction_add", check=check)

		index = emojis.index(reaction.emoji)

		if index == 1:
			i = 0
			message = await self._send_dm(sorciere, "Qui veux-tu tuer ? Choisis parmi cette liste : \n        ", "Sorcière")
			for member in self.game.members:
				if member != sorciere:
					msg = msg + str(i) + ". " + member.name + "\n        "
					i += 1

			for i in range(self.game.n_members - 1):
				await message.add_reaction(emojis[i])

			reaction, user = await self.wait_for("reaction_add", check=check)

			index = emojis.index(reaction.emoji)
			if index >= s_index:
				index += 1
			target = self.game.members[index]
			await self._send_dm(sorciere, f"{target.name} sera tué", "Sorcière")

			if target == self.game.current_victim:
				self.game.add_member_to_victims(self.game.current_victim)
			else:
				self.game.add_member_to_victims(self.game.current_victim)
				self.game.add_member_to_victims(target)
			self.game.remove_poison()
			return

		elif index == 0:
			await self._send_dm(sorciere, "Entendu !", "Sorcière")
			self.game.add_member_to_victims(self.game.current_victim)
			return

		self.game.remove_heal()
		await self._send_dm(sorciere, f"Tu viens de sauver {self.game.current_victim}", "Sorcière")

	async def vote(self, ctx: discord.Client):
		msg = "Vous devez maintenant voter pour une nouvelle victime\n"\
			"Attention, seulement votre première réaction est prise en compte, choisissez bien !\n\n\t"

		i = 0
		for member in self.game.members:
			msg = msg + str(i) + ". " + member.name + "\n\t"
			i += 1

		message = await self._send_context(msg, f"Tour n°{self.step}")

		emojis = ["0️⃣","1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]

		for i in range(self.game.n_members):
			await message.add_reaction(emojis[i])
		
		voted = []
		votes = {}

		def check(reaction, user):
			if str(reaction.emoji) in emojis[:self.game.n_members] and user.name not in voted and user.name != "LG":
				index = emojis.index(reaction.emoji)
				if self.game.members[index] not in votes.keys():
					votes[self.game.members[index]] = 1
				else:
					votes[self.game.members[index]] += 1
				voted.append(user.name)

				if len(voted) == len(self.game.members):
					return True

			return False

		reaction, user = await self.wait_for("reaction_add", check=check)

		maxvote = 0
		maxvote2 = 0

		for key, nb_votes in votes.items():
			if nb_votes > maxvote:
				victim = key
				maxvote2 = maxvote
				maxvote = nb_votes
			elif nb_votes > maxvote2:
				maxvote2 = nb_votes

		if maxvote == maxvote2:
			await self._send_context("Il faut se mettre d'accord sur les votes," \
				"quelqu'un doit mourir aujourd'hui, réessayez", "Vote")
			await message.delete()
			await self.vote(ctx)
		else:
			await self._send_context(f"Vous avez décidé de tuer {victim.name}...", "Vote")
			await self._send_context(f"{victim.name} était... {self.game.roles[victim]}", "Vote")
			if victim in self.game.couple:
				self.game.couple.remove(victim)
				couple = self.game.couple[0]
				await self._send_context(f"{victim.name} était en couple avec {couple}...\n "\
					f"{couple} avec le role {self.game.roles[couple]} meurt donc de chagrin")
				await self._kill(couple)
			await self._kill(victim)

######################################################################
######################################################################

	async def recap(self, ctx):
		await self._send_context(f"Le village se réveille !! Et...", "Journée")
		if len(self.game.daily_victims) == 0:
			await self._send_context(f"Personne n'est mort", "Journée")
		else:
			for victim in self.game.daily_victims:
				await self._send_context(f"{victim.name} est mort(e)\n Cette personne était {self.game.roles[victim]}", "Journée")
				if victim in self.game.couple:
					self.game.couple.remove(victim)
					couple = self.game.couple[0]
					await self._send_context(f"{victim.name} était en couple avec {couple}...\n "\
						f"{couple} avec le role {self.game.roles[couple]} meurt donc de chagrin", "Journée")
					await self._kill(couple)
				await self._kill(victim)