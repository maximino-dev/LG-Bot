# Config file
import os
from dotenv import load_dotenv

# discord
import discord
from discord.ext import commands

import bot

load_dotenv(dotenv_path="config")

intents = discord.Intents.default()
intents.members = True

help_command = commands.DefaultHelpCommand(
    no_category='Commands'
)

lg_bot = bot.LGBot(intents=intents, help_command=help_command)

lg_bot.run(os.getenv("TOKEN"))