import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
import os
import json
from datetime import datetime, timedelta
import asyncio
from dateutil.relativedelta import relativedelta

# Load environment variables
try:
    GUILD_ID = int(os.getenv("GUILD_ID"))
except (TypeError, ValueError):
    raise ValueError("GUILD_ID environment variable is not set or invalid. Please check the .env file.")

try:
    ALLOWED_DKP_SHOW_CHANNEL_ID = int(os.getenv("ALLOWED_DKP_SHOW_CHANNEL_ID"))
except (TypeError, ValueError):
    raise ValueError("ALLOWED_DKP_SHOW_CHANNEL_ID environment variable is not set or invalid. Please check the .env file.")

try:
    ALLOWED_ALLIANCE_DKP_ADDREMOVE_CHANNEL_ID = int(os.getenv("ALLOWED_ALLIANCE_DKP_ADDREMOVE_CHANNEL_ID"))
except (TypeError, ValueError):
    raise ValueError("ALLOWED_ALLIANCE_DKP_ADDREMOVE_CHANNEL_ID environment variable is not set or invalid. Please check the .env file.")

try:
    ALLOWED_ALLIANCE_DKP_SHOW_CHANNEL_ID = int(os.getenv("ALLOWED_ALLIANCE_DKP_SHOW_CHANNEL_ID"))
except (TypeError, ValueError):
    raise ValueError("ALLOWED_ALLIANCE_DKP_SHOW_CHANNEL_ID environment variable is not set or invalid. Please check the .env file.")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
MEMBER_ROLE = os.getenv("MEMBER_ROLE")
OFFICER_ROLE = os.getenv("OFFICER_ROLE")
ALLOWED_CLANS = os.getenv("ALLOWED_CLANS", "").split(",")  # Comma-separated list
ALLIANCE_LEADER_ROLE = os.getenv("ALLIANCE_LEADER_ROLE")

# Configure logging
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

# Initialize bot and intents
intents = discord.Intents.default()
intents.members = True  # Required to access guild member information
bot = commands.Bot(command_prefix="!", intents=intents)
dkp_data_file = "dkp_data.json"
leaderboard_data_file = "leaderboard_data.json"
dkp_archive_file = "dkp_archive.json"
alliance_dkp_data_file = "alliance_dkp_data.json"

# Ensure DKP and leaderboard data files exist
def ensure_data_files():
    for file in [dkp_data_file, leaderboard_data_file, dkp_archive_file, alliance_dkp_data_file]:
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

# Function to handle role changes
async def add_member_to_leaderboards(member: discord.Member):
    dkp_data = load_data(dkp_data_file)
    leaderboard_data = load_data(leaderboard_data_file)
    archive_data = load_data(dkp_archive_file)

    member_id = str(member.id)

    if member_id in archive_data:
        # Restore DKP from archive
        dkp_data[member_id] = archive_data.pop(member_id)
        save_data(dkp_archive_file, archive_data)
    elif member_id not in dkp_data:
        dkp_data[member_id] = 0

    current_month = datetime.now().strftime("%Y-%m")
    if member_id not in leaderboard_data:
        leaderboard_data[member_id] = {}
    if current_month not in leaderboard_data[member_id]:
        leaderboard_data[member_id][current_month] = 0

    save_data(dkp_data_file, dkp_data)
    save_data(leaderboard_data_file, leaderboard_data)

async def remove_member_from_leaderboards(member: discord.Member):
    dkp_data = load_data(dkp_data_file)
    leaderboard_data = load_data(leaderboard_data_file)
    archive_data = load_data(dkp_archive_file)

    member_id = str(member.id)

    if member_id in dkp_data:
        archive_data[member_id] = dkp_data.pop(member_id)
        leaderboard_data.pop(member_id)
        save_data(dkp_data_file, dkp_data)
        save_data(leaderboard_data_file, leaderboard_data)
        save_data(dkp_archive_file, archive_data)

# Events for role updates
@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    guild = after.guild
    role = discord.utils.get(guild.roles, name=MEMBER_ROLE)

    if role in after.roles and role not in before.roles:
        await add_member_to_leaderboards(after)
    elif role not in after.roles and role in before.roles:
        await remove_member_from_leaderboards(after)

# Initialize leaderboard from current members
async def initialize_leaderboard():
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        logger.error("Guild not found. Ensure the bot is added to the guild and the GUILD_ID is correct.")
        return

    role = discord.utils.get(guild.roles, name=MEMBER_ROLE)
    if not role:
        logger.error(f"Role '{MEMBER_ROLE}' not found in the guild.")
        return

    for member in guild.members:
        if role in member.roles:
            await add_member_to_leaderboards(member)

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
        self.bot.tree.add_command(self.dkp_archive, guild=discord.Object(id=GUILD_ID))
        self.bot.tree.add_command(self.dkp_alliance_add, guild=discord.Object(id=GUILD_ID))
        self.bot.tree.add_command(self.dkp_alliance_remove, guild=discord.Object(id=GUILD_ID))
        self.bot.tree.add_command(self.dkp_alliance_show, guild=discord.Object(id=GUILD_ID))


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
        if not interaction.user.guild_permissions.administrator and not any(role.name == OFFICER_ROLE for role in interaction.user.roles):
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return
        
        if not any(role.name == MEMBER_ROLE for role in member.roles):
            await interaction.response.send_message("Target is not a Member.", ephemeral=True)
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

        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return
        
        if not any(role.name == MEMBER_ROLE for role in member.roles):
            await interaction.response.send_message("Target is not a Member.", ephemeral=True)
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
        
        if not any(role.name == MEMBER_ROLE for role in member.roles):
            await interaction.response.send_message("Target is not a Member.", ephemeral=True)
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
        
        if interaction.channel.id != ALLOWED_DKP_SHOW_CHANNEL_ID:
            await interaction.response.send_message("This command can only be used in a #dkp channel.", ephemeral=True)
            return

        if not any(role.name == MEMBER_ROLE for role in interaction.user.roles):
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        # Load current DKP data
        dkp_data = load_data(dkp_data_file)

        member_id = str(interaction.user.id if member is None else member.id)
        current_dkp = dkp_data.get(member_id, 0)
        target = "your" if member is None else f"{member.mention}'s"

        await interaction.response.send_message(f"{interaction.user.mention}, {target} current DKP is: {current_dkp}")

    @app_commands.command(name="dkp_archive", description="Show archived DKP data (admin only).")
    async def dkp_archive(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        archive_data = load_data(dkp_archive_file)
        if not archive_data:
            await interaction.response.send_message("The DKP archive is empty.", ephemeral=True)
            return

        archive_message = "**DKP Archive:**\n" + "\n".join(
            [f"<@{member_id}>: {dkp}" for member_id, dkp in archive_data.items()]
        )
        await interaction.response.send_message(archive_message)

    @app_commands.command(name="dkp_leaderboard", description="Show the DKP leaderboard.")
    @app_commands.describe(
        time_frame="Time frame for the leaderboard: 'overall', 'current', or 'last' (default: overall)."
    )
    async def dkp_leaderboard(self, interaction: discord.Interaction, time_frame: str = "overall"):
        if interaction.guild.id != GUILD_ID:
            await interaction.response.send_message("This command is not available in this guild.", ephemeral=True)
            return
        
        #if not interaction.user.guild_permissions.manage_guild:
        if not interaction.user.guild_permissions.administrator and not any(role.name == OFFICER_ROLE for role in interaction.user.roles):
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        dkp_data = load_data(dkp_data_file)
        leaderboard_data = load_data(leaderboard_data_file)

        if time_frame.lower() == "current":
            current_month = datetime.now().strftime("%Y-%m")
            monthly_leaderboard = {
                member_id: months.get(current_month, 0)
                for member_id, months in leaderboard_data.items()
            }
            sorted_leaderboard = sorted(monthly_leaderboard.items(), key=lambda x: x[1], reverse=True)
            leaderboard_message = "**Current Month DKP Leaderboard:**\n"
        elif time_frame.lower() == "last":
            last_month = (datetime.now() - relativedelta(months=1)).strftime("%Y-%m")
            monthly_leaderboard = {
                member_id: months.get(last_month, 0)
                for member_id, months in leaderboard_data.items()
            }
            sorted_leaderboard = sorted(monthly_leaderboard.items(), key=lambda x: x[1], reverse=True)
            leaderboard_message = "**Last Month DKP Leaderboard:**\n"
        else:
            sorted_leaderboard = sorted(dkp_data.items(), key=lambda x: x[1], reverse=True)
            leaderboard_message = "**Overall DKP Leaderboard:**\n"

        leaderboard_table = [f"{idx + 1}. <@{member_id}>: {dkp}" for idx, (member_id, dkp) in enumerate(sorted_leaderboard)]
        leaderboard_message += "\n".join(leaderboard_table)

        await interaction.response.send_message(leaderboard_message)

    @app_commands.command(name="dkp_alliance_add", description="Add DKP to an clan in the alliance.")
    @app_commands.describe(
        member="The clan to add DKP to.",
        amount="The amount of DKP to add."
    )
    async def dkp_alliance_add(self, interaction: discord.Interaction, member: str, amount: int):
        if interaction.guild.id != GUILD_ID:
            await interaction.response.send_message("This command is not available in this guild.", ephemeral=True)
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        if interaction.channel.id != ALLOWED_ALLIANCE_DKP_ADDREMOVE_CHANNEL_ID:
            await interaction.response.send_message("This command can only be used in the allowed channel.", ephemeral=True)
            return

        if member not in ALLOWED_CLANS:
            await interaction.response.send_message("Invalid clan selection.", ephemeral=True)
            return

        if amount < 0:
            await interaction.response.send_message("Amount must be a non-negative integer.", ephemeral=True)
            return

        dkp_data = load_data(alliance_dkp_data_file)

        dkp_data[member] = dkp_data.get(member, 0) + amount
        save_data(alliance_dkp_data_file, dkp_data)

        logger.info(f"{interaction.user.name} added {amount} DKP for {member} clan. New DKP: {dkp_data[member]}")

        await interaction.response.send_message(
            f"Added {amount} DKP to {member} clan. Current DKP: {dkp_data[member]}")

    @app_commands.command(name="dkp_alliance_remove", description="Remove DKP from a clan in the alliance.")
    @app_commands.describe(
        member="Select the clan to remove DKP from.",
        amount="The amount of DKP to remove."
    )
    async def dkp_alliance_remove(self, interaction: discord.Interaction, member: str, amount: int):
        if interaction.channel.id != ALLOWED_ALLIANCE_DKP_ADDREMOVE_CHANNEL_ID:
            await interaction.response.send_message("This command can only be used in the allowed channel.", ephemeral=True)
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        if member not in ALLOWED_CLANS:
            await interaction.response.send_message("Invalid clan selection.", ephemeral=True)
            return

        if amount < 0:
            await interaction.response.send_message("Amount must be a non-negative integer.", ephemeral=True)
            return

        dkp_data = load_data(alliance_dkp_data_file)

        if member not in dkp_data:
            dkp_data[member] = 0

        if dkp_data[member] < amount:
            await interaction.response.send_message(f"You cannot remove more DKP than the clan has. Current DKP: {dkp_data[member]}", ephemeral=True)
            return

        dkp_data[member] = max(0, dkp_data[member] - amount)
        save_data(alliance_dkp_data_file, dkp_data)

        logger.info(f"{interaction.user.name} removed {amount} DKP from {member} clan. New DKP: {dkp_data[member]}")

        await interaction.response.send_message(
            f"Removed {amount} DKP from {member} clan. Current DKP: {dkp_data[member]}")

    @app_commands.command(name="dkp_alliance_show", description="Show the current DKP of a clan in the alliance.")
    @app_commands.describe(
        member="The clan whose DKP to view."
    )
    async def dkp_alliance_show(self, interaction: discord.Interaction, member: str):
        if interaction.channel.id != ALLOWED_ALLIANCE_DKP_SHOW_CHANNEL_ID:
            await interaction.response.send_message("This command can only be used in the designated DKP channel.",
                                                    ephemeral=True)
            return

        if not interaction.user.guild_permissions.administrator and not any(role.name == ALLIANCE_LEADER_ROLE for role in interaction.user.roles):
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        dkp_data = load_data(alliance_dkp_data_file)

        member = member or "alliance"
        current_dkp = dkp_data.get(member, 0)

        await interaction.response.send_message(
            f"{interaction.user.mention}, {member}'s current DKP is: {current_dkp}")

    @dkp_alliance_add.autocomplete("member")
    @dkp_alliance_remove.autocomplete("member")
    @dkp_alliance_show.autocomplete("member")
    async def member_autocomplete(self, interaction: discord.Interaction, current: str):
        return [app_commands.Choice(name=clan, value=clan) for clan in ALLOWED_CLANS if current.lower() in clan.lower()]


@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user}!")
    try:
        # # Clear cached commands and sync
        # await bot.tree.clear_commands(guild=discord.Object(id=GUILD_ID))
        # logger.info("Cleared cached commands.")

        # Load the cog
        await setup()

        await initialize_leaderboard()

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
