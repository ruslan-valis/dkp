import discord
from discord.ext import commands
from discord import app_commands
import logging
import os
import json
from datetime import datetime

# Load environment variables
try:
    GUILD_ID = int(os.getenv("GUILD_ID"))
except (TypeError, ValueError):
    raise ValueError("GUILD_ID environment variable is not set or invalid. Please check the .env file.")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OFFICER_ROLE = os.getenv("OFFICER_ROLE")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Configure logging
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

# Initialize bot and intents
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
dkp_data_file = "dkp_data.json"
leaderboard_data_file = "leaderboard_data.json"

# Ensure DKP and leaderboard data files exist
def ensure_data_files():
    for file in [dkp_data_file, leaderboard_data_file]:
        if not os.path.exists(file):
            with open(file, "w") as f:
                json.dump({}, f)

ensure_data_files()

# Load and save data
def load_data(file):
    with open(file, "r") as f:
        return json.load(f)

def save_data(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=4)

# DKP management cog
class DKPManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Bind commands to the specific guild
        self.bot.tree.add_command(self.dkp_add, guild=discord.Object(id=GUILD_ID))
        self.bot.tree.add_command(self.dkp_remove, guild=discord.Object(id=GUILD_ID))
        self.bot.tree.add_command(self.dkp_cancel, guild=discord.Object(id=GUILD_ID))
        self.bot.tree.add_command(self.dkp_show, guild=discord.Object(id=GUILD_ID))
        self.bot.tree.add_command(self.dkp_leaderboard, guild=discord.Object(id=GUILD_ID))

    @app_commands.command(name="dkp_add", description="Add DKP to a guild member.")
    @app_commands.describe(
        member="The member to add DKP to.",
        amount="The amount of DKP to add."
    )
    async def dkp_add(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if interaction.guild.id != GUILD_ID:
            await interaction.response.send_message("This command is not available in this guild.", ephemeral=True)
            return

        #if not interaction.user.guild_permissions.manage_guild:
        if not any(role.name == OFFICER_ROLE for role in interaction.user.roles):
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        if amount < 0:
            await interaction.response.send_message("Amount must be a non-negative integer.", ephemeral=True)
            return

        # Load current DKP and leaderboard data
        dkp_data = load_data(dkp_data_file)
        leaderboard_data = load_data(leaderboard_data_file)

        member_id = str(member.id)
        if member_id not in dkp_data:
            dkp_data[member_id] = 0

        dkp_data[member_id] += amount
        save_data(dkp_data_file, dkp_data)

        # Update monthly leaderboard
        current_month = datetime.now().strftime("%Y-%m")
        if member_id not in leaderboard_data:
            leaderboard_data[member_id] = {}
        if current_month not in leaderboard_data[member_id]:
            leaderboard_data[member_id][current_month] = 0

        leaderboard_data[member_id][current_month] += amount
        save_data(leaderboard_data_file, leaderboard_data)

        logger.info(f"{interaction.user.name} added {amount} DKP for {member.name}. New DKP: {dkp_data[member_id]}")

        await interaction.response.send_message(f"Added {amount} DKP to {member.mention}. Current DKP: {dkp_data[member_id]}")

    @app_commands.command(name="dkp_remove", description="Remove DKP from a guild member.")
    @app_commands.describe(
        member="The member to remove DKP from.",
        amount="The amount of DKP to remove."
    )
    async def dkp_remove(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if interaction.guild.id != GUILD_ID:
            await interaction.response.send_message("This command is not available in this guild.", ephemeral=True)
            return

        #if not interaction.user.guild_permissions.manage_guild:
        if not any(role.name == OFFICER_ROLE for role in interaction.user.roles):
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        if amount < 0:
            await interaction.response.send_message("Amount must be a non-negative integer.", ephemeral=True)
            return

        # Load current DKP data
        dkp_data = load_data(dkp_data_file)

        member_id = str(member.id)
        if member_id not in dkp_data:
            dkp_data[member_id] = 0

        if dkp_data[member_id] < amount:
            await interaction.response.send_message(f"You cant remove more DKP than member have. Current {member.mention} DKP is: {dkp_data[member_id]}", ephemeral=True)
            return

        dkp_data[member_id] = max(0, dkp_data[member_id] - amount)
        save_data(dkp_data_file, dkp_data)
        logger.info(f"{interaction.user.name} removed {amount} DKP from {member.name}. New DKP: {dkp_data[member_id]}")

        await interaction.response.send_message(f"Removed {amount} DKP from {member.mention}. Current DKP: {dkp_data[member_id]}")


    @app_commands.command(name="dkp_cancel", description="Cancel DKP from a guild member, including removing from monthly leaderboard.")
    @app_commands.describe(
        member="The member to remove DKP from.",
        amount="The amount of DKP to remove."
    )
    async def dkp_cancel(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if interaction.guild.id != GUILD_ID:
            await interaction.response.send_message("This command is not available in this guild.", ephemeral=True)
            return

        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        if amount < 0:
            await interaction.response.send_message("Amount must be a non-negative integer.", ephemeral=True)
            return

        # Load current DKP and leaderboard data
        dkp_data = load_data(dkp_data_file)
        leaderboard_data = load_data(leaderboard_data_file)

        member_id = str(member.id)
        if member_id not in dkp_data:
            dkp_data[member_id] = 0

        if dkp_data[member_id] < amount:
            await interaction.response.send_message(f"You cant remove more DKP than member have. Current {member.mention} DKP is: {dkp_data[member_id]}", ephemeral=True)
            return

        dkp_data[member_id] = max(0, dkp_data[member_id] - amount)
        save_data(dkp_data_file, dkp_data)

        # Update monthly leaderboard
        current_month = datetime.now().strftime("%Y-%m")
        if member_id not in leaderboard_data:
            leaderboard_data[member_id] = {}
        if current_month not in leaderboard_data[member_id]:
            leaderboard_data[member_id][current_month] = 0

        leaderboard_data[member_id][current_month] -= amount
        save_data(leaderboard_data_file, leaderboard_data)
        
        logger.info(f"{interaction.user.name} removed {amount} DKP from {member.name}. New DKP: {dkp_data[member_id]}")

        await interaction.response.send_message(f"Canceled {amount} DKP from {member.mention}. Current DKP: {dkp_data[member_id]}")

    @app_commands.command(name="dkp_show", description="Show the current DKP of a guild member.")
    @app_commands.describe(
        member="The member whose DKP to view (optional)."
    )
    async def dkp_show(self, interaction: discord.Interaction, member: discord.Member = None):
        if interaction.guild.id != GUILD_ID:
            await interaction.response.send_message("This command is not available in this guild.", ephemeral=True)
            return

        # Load current DKP data
        dkp_data = load_data(dkp_data_file)

        member_id = str(interaction.user.id if member is None else member.id)
        current_dkp = dkp_data.get(member_id, 0)
        target = "your" if member is None else f"{member.mention}'s"

        await interaction.response.send_message(f"{interaction.user.mention}, {target} current DKP is: {current_dkp}")

    @app_commands.command(name="dkp_leaderboard", description="Show the DKP leaderboard.")
    @app_commands.describe(
        time_frame="Time frame for the leaderboard: 'overall' or 'month' (default: overall)."
    )
    async def dkp_leaderboard(self, interaction: discord.Interaction, time_frame: str = "overall"):
        if interaction.guild.id != GUILD_ID:
            await interaction.response.send_message("This command is not available in this guild.", ephemeral=True)
            return
        
        #if not interaction.user.guild_permissions.manage_guild:
        if not any(role.name == OFFICER_ROLE for role in interaction.user.roles):
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        dkp_data = load_data(dkp_data_file)
        leaderboard_data = load_data(leaderboard_data_file)

        if time_frame.lower() == "month":
            current_month = datetime.now().strftime("%Y-%m")
            monthly_leaderboard = {
                member_id: months.get(current_month, 0)
                for member_id, months in leaderboard_data.items()
            }
            sorted_leaderboard = sorted(monthly_leaderboard.items(), key=lambda x: x[1], reverse=True)
            leaderboard_message = "**Monthly DKP Leaderboard:**\n" + "\n".join(
                [f"<@{member_id}>: {dkp}" for member_id, dkp in sorted_leaderboard]
            )
        else:
            sorted_leaderboard = sorted(dkp_data.items(), key=lambda x: x[1], reverse=True)
            leaderboard_message = "**Overall DKP Leaderboard:**\n" + "\n".join(
                [f"<@{member_id}>: {dkp}" for member_id, dkp in sorted_leaderboard]
            )

        await interaction.response.send_message(leaderboard_message)

@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user}!")
    try:
        # # Clear cached commands and sync
        # await bot.tree.clear_commands(guild=discord.Object(id=GUILD_ID))
        # logger.info("Cleared cached commands.")

        # Load the cog
        await setup()

        # Sync the commands for the specific guild
        guild = discord.Object(id=GUILD_ID)
        synced = await bot.tree.sync(guild=guild)

        logger.info(f"Synced {len(synced)} command(s) with the guild {GUILD_ID}.")
        logger.info(f"Available commands: {[cmd.name for cmd in synced]}")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")

async def setup():
    await bot.add_cog(DKPManager(bot))
    logger.info("DKPManager cog has been loaded.")

bot.run(DISCORD_TOKEN)
