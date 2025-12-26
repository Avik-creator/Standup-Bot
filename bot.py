import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

import database

# Load environment variables
load_dotenv()

# Bot configuration
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN not found in environment variables")

if not GUILD_ID:
    raise ValueError("GUILD_ID not found in environment variables")


# Bot setup with required intents
intents = discord.Intents.default()
intents.message_content = True  # Required for reading message content
intents.members = True          # Required for accessing member list
intents.dm_messages = True      # Required for DM handling

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    description="Daily Standup Bot"
)


# List of cogs to load
COGS = [
    "cogs.registration",
    "cogs.collection",
    "cogs.admin", 
    "cogs.scheduler"
]


@bot.event
async def on_ready():
    """Called when the bot is ready."""
    # Sync slash commands with Discord
    try:
        guild = discord.Object(id=int(GUILD_ID))
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"synced {len(synced)} slash commands to guild")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    
    print(f"{'='*50}")
    print(f"Bot is ready!")
    print(f"Logged in as: {bot.user.name} ({bot.user.id})")
    print(f"Guild ID: {GUILD_ID}")
    print(f"{'='*50}")
    
    # Set bot status
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="for standups | /standup_help"
        )
    )


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    """Global error handler."""
    if isinstance(error, commands.CommandNotFound):
        return  # Ignore unknown commands
    
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing argument: `{error.param.name}`")
        return
    
    # Log other errors
    print(f"[Error] {type(error).__name__}: {error}")


async def load_cogs():
    """Load all cogs."""
    for cog in COGS:
        try:
            await bot.load_extension(cog)
            print(f"Loaded cog: {cog}")
        except Exception as e:
            print(f"Failed to load cog {cog}: {e}")


async def main():
    """Main entry point."""
    # Initialize database
    database.init_db()
    print("Database initialized")
    
    # Load cogs
    async with bot:
        await load_cogs()
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
