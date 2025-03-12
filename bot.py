import discord
from discord.ext import commands, tasks
from discord.ui import View, Select, Button, TextInput, Modal
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

try:
    TRANSFER_CHANNEL_ID = int(os.getenv("TRANSFER_CHANNEL_ID"))
except (TypeError, ValueError):
    raise ValueError("TRANSFER_CHANNEL_ID environment variable is not set or invalid. Please check the .env file.")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
MEMBER_ROLE = os.getenv("MEMBER_ROLE")
OFFICER_ROLE = os.getenv("OFFICER_ROLE")
ALLOWED_CLANS = os.getenv("ALLOWED_CLANS", "").split(",")  # Comma-separated list
ALLOWED_EVENTS_LIST = os.getenv("ALLOWED_EVENTS_LIST", "").split(",")  # Comma-separated list
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

# Trade DKP
TRADE_PINNED_MESSAGE_FILE = "trade_message.json"

def save_trade_pinned_message_id(trade_message_id):
    with open(TRADE_PINNED_MESSAGE_FILE, "w") as f:
        json.dump({"trade_pinned_message_id": trade_message_id}, f)

def load_trade_pinned_message_id():
    if os.path.exists(TRADE_PINNED_MESSAGE_FILE):
        with open(TRADE_PINNED_MESSAGE_FILE, "r") as f:
            data = json.load(f)
            return data.get("trade_pinned_message_id")
    return None

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
        # Use defer to avoid timeout issues
        await interaction.response.defer()

        if interaction.guild.id != GUILD_ID:
            await interaction.followup.send("This command is not available in this guild.", ephemeral=True)
            return

        #if not interaction.user.guild_permissions.manage_guild:
        if not interaction.user.guild_permissions.administrator and not any(role.name == OFFICER_ROLE for role in interaction.user.roles):
            await interaction.followup.send("You do not have permission to use this command.", ephemeral=True)
            return
        
        if not any(role.name == MEMBER_ROLE for role in member.roles):
            await interaction.followup.send("Target is not a Member.", ephemeral=True)
            return

        if amount < 0:
            await interaction.followup.send("Amount must be a non-negative integer.", ephemeral=True)
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

        await interaction.followup.send(f"Added {amount} DKP to {member.mention}. Current DKP: {dkp_data[member_id]}")

    @app_commands.command(name="dkp_remove", description="Remove DKP from a guild member.")
    @app_commands.describe(
        member="The member to remove DKP from.",
        amount="The amount of DKP to remove."
    )
    async def dkp_remove(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        # Use defer to avoid timeout issues
        await interaction.response.defer()

        if interaction.guild.id != GUILD_ID:
            await interaction.followup.send("This command is not available in this guild.", ephemeral=True)
            return

        if not interaction.user.guild_permissions.manage_guild:
            await interaction.followup.send("You do not have permission to use this command.", ephemeral=True)
            return
        
        if not any(role.name == MEMBER_ROLE for role in member.roles):
            await interaction.followup.send("Target is not a Member.", ephemeral=True)
            return

        if amount < 0:
            await interaction.followup.send("Amount must be a non-negative integer.", ephemeral=True)
            return

        # Load current DKP data
        dkp_data = load_data(dkp_data_file)

        member_id = str(member.id)
        if member_id not in dkp_data:
            dkp_data[member_id] = 0

        if dkp_data[member_id] < amount:
            await interaction.followup.send(f"You cant remove more DKP than member have. Current {member.mention} DKP is: {dkp_data[member_id]}", ephemeral=True)
            return

        dkp_data[member_id] = max(0, dkp_data[member_id] - amount)
        save_data(dkp_data_file, dkp_data)
        logger.info(f"{interaction.user.name} removed {amount} DKP from {member.name}. New DKP: {dkp_data[member_id]}")

        await interaction.followup.send(f"Removed {amount} DKP from {member.mention}. Current DKP: {dkp_data[member_id]}")


    @app_commands.command(name="dkp_cancel", description="Cancel DKP from a guild member, including removing from monthly leaderboard.")
    @app_commands.describe(
        member="The member to remove DKP from.",
        amount="The amount of DKP to remove."
    )
    async def dkp_cancel(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        # Use defer to avoid timeout issues
        await interaction.response.defer()

        if interaction.guild.id != GUILD_ID:
            await interaction.followup.send("This command is not available in this guild.", ephemeral=True)
            return

        if not interaction.user.guild_permissions.manage_guild:
            await interaction.followup.send("You do not have permission to use this command.", ephemeral=True)
            return
        
        if not any(role.name == MEMBER_ROLE for role in member.roles):
            await interaction.followup.send("Target is not a Member.", ephemeral=True)
            return

        if amount < 0:
            await interaction.followup.send("Amount must be a non-negative integer.", ephemeral=True)
            return

        # Load current DKP and leaderboard data
        dkp_data = load_data(dkp_data_file)
        leaderboard_data = load_data(leaderboard_data_file)

        member_id = str(member.id)
        if member_id not in dkp_data:
            dkp_data[member_id] = 0

        if dkp_data[member_id] < amount:
            await interaction.followup.send(f"You cant remove more DKP than member have. Current {member.mention} DKP is: {dkp_data[member_id]}", ephemeral=True)
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

        await interaction.followup.send(f"Canceled {amount} DKP from {member.mention}. Current DKP: {dkp_data[member_id]}")

    @app_commands.command(name="dkp_show", description="Show the current DKP of a guild member.")
    @app_commands.describe(
        member="The member whose DKP to view (optional)."
    )
    async def dkp_show(self, interaction: discord.Interaction, member: discord.Member = None):
        # Use defer to avoid timeout issues
        await interaction.response.defer()

        if interaction.guild.id != GUILD_ID:
            await interaction.followup.send("This command is not available in this guild.", ephemeral=True)
            return
        
        if interaction.channel.id != ALLOWED_DKP_SHOW_CHANNEL_ID:
            await interaction.followup.send("This command can only be used in a #dkp channel.", ephemeral=True)
            return

        if not any(role.name == MEMBER_ROLE for role in interaction.user.roles):
            await interaction.followup.send("You do not have permission to use this command.", ephemeral=True)
            return

        # Load current DKP data
        dkp_data = load_data(dkp_data_file)

        member_id = str(interaction.user.id if member is None else member.id)
        current_dkp = dkp_data.get(member_id, 0)
        target = "your" if member is None else f"{member.mention}'s"

        await interaction.followup.send(f"{interaction.user.mention}, {target} current DKP is: {current_dkp}")

    @app_commands.command(name="dkp_archive", description="Show archived DKP data (admin only).")
    async def dkp_archive(self, interaction: discord.Interaction):
        # Use defer to avoid timeout issues
        await interaction.response.defer()

        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("You do not have permission to use this command.", ephemeral=True)
            return

        archive_data = load_data(dkp_archive_file)
        if not archive_data:
            await interaction.followup.send("The DKP archive is empty.", ephemeral=True)
            return

        archive_message = "**DKP Archive:**\n" + "\n".join(
            [f"<@{member_id}>: {dkp}" for member_id, dkp in archive_data.items()]
        )
        await interaction.followup.send(archive_message)

    @app_commands.command(name="dkp_leaderboard", description="Show the DKP leaderboard.")
    @app_commands.describe(
        time_frame="Time frame for the leaderboard: 'overall', 'current', or 'last' (default: overall)."
    )
    async def dkp_leaderboard(self, interaction: discord.Interaction, time_frame: str = "overall"):
        # Use defer to avoid timeout issues
        await interaction.response.defer()

        if interaction.guild.id != GUILD_ID:
            await interaction.followup.send("This command is not available in this guild.", ephemeral=True)
            return
        
        #if not interaction.user.guild_permissions.manage_guild:
        if not interaction.user.guild_permissions.administrator and not any(role.name == OFFICER_ROLE for role in interaction.user.roles):
            await interaction.followup.send("You do not have permission to use this command.", ephemeral=True)
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

        await interaction.followup.send(leaderboard_message)

    @app_commands.command(name="dkp_alliance_add", description="Add DKP to an clan in the alliance.")
    @app_commands.describe(
        event_type="The event type to add DKP to.",
        member="The clan to add DKP to.",
        amount="The amount of DKP to add."
    )
    async def dkp_alliance_add(self, interaction: discord.Interaction, event_type: str, member: str, amount: int):
        # Use defer to avoid timeout issues
        await interaction.response.defer()

        if interaction.guild.id != GUILD_ID:
            await interaction.followup.send("This command is not available in this guild.", ephemeral=True)
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("You do not have permission to use this command.", ephemeral=True)
            return

        if interaction.channel.id != ALLOWED_ALLIANCE_DKP_ADDREMOVE_CHANNEL_ID and (
                not isinstance(interaction.channel,
                               discord.Thread) or interaction.channel.parent_id != ALLOWED_ALLIANCE_DKP_ADDREMOVE_CHANNEL_ID
        ):
            await interaction.followup.send("This command can only be used in the allowed channel.", ephemeral=True)
            return

        if event_type not in ALLOWED_EVENTS_LIST:
            await interaction.followup.send("Invalid event type selection.", ephemeral=True)
            return

        if member not in ALLOWED_CLANS:
            await interaction.followup.send("Invalid clan selection.", ephemeral=True)
            return

        if amount < 0:
            await interaction.followup.send("Amount must be a non-negative integer.", ephemeral=True)
            return

        dkp_data = load_data(alliance_dkp_data_file)

        if member not in dkp_data:
            dkp_data[member] = {}
        if event_type not in dkp_data[member]:
            dkp_data[member][event_type] = 0

        dkp_data[member][event_type] += amount

        save_data(alliance_dkp_data_file, dkp_data)

        logger.info(f"{interaction.user.name} added {amount} DKP for {member} clan. New DKP {event_type}: {dkp_data[member][event_type]}")

        await interaction.followup.send(
            f"Added {amount} DKP to {member} clan. Current DKP for event {event_type}: {dkp_data[member][event_type]}")

    @app_commands.command(name="dkp_alliance_remove", description="Remove DKP from a clan in the alliance.")
    @app_commands.describe(
        event_type="The event type to remove DKP from.",
        member="Select the clan to remove DKP from.",
        amount="The amount of DKP to remove."
    )
    async def dkp_alliance_remove(self, interaction: discord.Interaction, event_type: str, member: str, amount: int):
        # Use defer to avoid timeout issues
        await interaction.response.defer()

        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("You do not have permission to use this command.", ephemeral=True)
            return

        if event_type not in ALLOWED_EVENTS_LIST:
            await interaction.followup.send("Invalid event type selection.", ephemeral=True)
            return

        if member not in ALLOWED_CLANS:
            await interaction.followup.send("Invalid clan selection.", ephemeral=True)
            return

        if amount < 0:
            await interaction.followup.send("Amount must be a non-negative integer.", ephemeral=True)
            return

        dkp_data = load_data(alliance_dkp_data_file)

        if member not in dkp_data:
            dkp_data[member] = {}
        if event_type not in dkp_data[member]:
            dkp_data[member][event_type] = 0

        if dkp_data[member][event_type] < amount:
            await interaction.followup.send(f"You cannot remove more DKP than the clan has. Current DKP for event {event_type}: {dkp_data[member][event_type]}", ephemeral=True)
            return

        dkp_data[member][event_type] = max(0, dkp_data[member][event_type] - amount)
        save_data(alliance_dkp_data_file, dkp_data)

        logger.info(f"{interaction.user.name} removed {amount} DKP from {member} clan. New DKP for event {event_type}: {dkp_data[member][event_type]}")

        await interaction.followup.send(
            f"Removed {amount} DKP from {member} clan. Current DKP for event {event_type}: {dkp_data[member][event_type]}")

    @app_commands.command(name="dkp_alliance_show", description="Show the current DKP of a clan in the alliance.")
    @app_commands.describe(
        event_type="The event type to show DKP for.",
        member="The clan whose DKP to view."
    )
    async def dkp_alliance_show(self, interaction: discord.Interaction, event_type: str, member: str):
        # Use defer to avoid timeout issues
        await interaction.response.defer()

        if interaction.channel.id != ALLOWED_ALLIANCE_DKP_SHOW_CHANNEL_ID:
            await interaction.followup.send("This command can only be used in the designated DKP channel.",
                                                    ephemeral=True)
            return

        if not interaction.user.guild_permissions.administrator and not any(role.name == ALLIANCE_LEADER_ROLE for role in interaction.user.roles):
            await interaction.followup.send("You do not have permission to use this command.", ephemeral=True)
            return

        if event_type not in ALLOWED_EVENTS_LIST:
            await interaction.followup.send("Invalid event type selection.", ephemeral=True)
            return

        if member not in ALLOWED_CLANS:
            await interaction.followup.send("Invalid clan selection.", ephemeral=True)
            return

        dkp_data = load_data(alliance_dkp_data_file)

        member = member or "alliance"
        current_member = dkp_data.get(member, {})
        current_dkp = current_member.get(event_type, 0)

        await interaction.followup.send(
            f"{interaction.user.mention}, {member}'s current DKP for event {event_type} is: {current_dkp}")

    @dkp_alliance_add.autocomplete("member")
    @dkp_alliance_remove.autocomplete("member")
    @dkp_alliance_show.autocomplete("member")
    async def member_autocomplete(self, interaction: discord.Interaction, current: str):
        return [app_commands.Choice(name=clan, value=clan) for clan in ALLOWED_CLANS if current.lower() in clan.lower()]

    @dkp_alliance_add.autocomplete("event_type")
    @dkp_alliance_remove.autocomplete("event_type")
    @dkp_alliance_show.autocomplete("event_type")
    async def member_autocomplete(self, interaction: discord.Interaction, current: str):
        return [app_commands.Choice(name=event_name, value=event_name) for event_name in ALLOWED_EVENTS_LIST if current.lower() in event_name.lower()]


class DKPDropdown(discord.ui.Select):
    def __init__(self, members):
        options = [discord.SelectOption(label=member.display_name, value=str(member.id)) for member in members]
        super().__init__(placeholder="Виберіть члена клану", options=options)

    async def callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        target_id = int(self.values[0])
        await interaction.response.send_modal(DKPTransferModal(user_id, target_id))


class DKPTransferModal(discord.ui.Modal, title="Передача DKP"):
    def __init__(self, sender_id, receiver_id):
        super().__init__()
        self.sender_id = sender_id
        self.receiver_id = receiver_id
        self.dkp_amount = discord.ui.TextInput(label="Введіть кількість DKP", style=discord.TextStyle.short)
        self.add_item(self.dkp_amount)

    async def on_submit(self, interaction: discord.Interaction):
        dkp_data = load_data(dkp_data_file)
        sender_id = str(self.sender_id)
        receiver_id = str(self.receiver_id)

        sender_balance = dkp_data.get(sender_id, 0)
        transfer_amount = int(self.dkp_amount.value)

        # Use defer to avoid timeout issues
        await interaction.response.defer()

        # Ensure receiver_id is set
        if self.sender_id is None:
            await interaction.followup.send("Помилка: Не вдалося знайти відправника.", ephemeral=True)
            return

        # Ensure receiver_id is set
        if self.receiver_id is None:
            await interaction.followup.send("Помилка: Не вдалося знайти отримувача.", ephemeral=True)
            return

        if self.sender_id == self.receiver_id:
            await interaction.followup.send("Ви не можете відправиди DKP самі собі!", ephemeral=True)
            return

        if transfer_amount <= 0:
            await interaction.followup.send(f"Ви не можете відправити відємне значення або нуль.", ephemeral=True)
            return

        if transfer_amount > sender_balance:
            await interaction.followup.send(f"Недостатньо DKP! Ви маєте: {sender_balance}", ephemeral=True)
            return

        dkp_data[sender_id] -= transfer_amount
        dkp_data[receiver_id] = dkp_data.get(receiver_id, 0) + transfer_amount
        save_data(dkp_data_file, dkp_data)

        sender = interaction.guild.get_member(self.sender_id)
        receiver = interaction.guild.get_member(self.receiver_id)
        await interaction.followup.send(
            f"{sender.mention} передав {transfer_amount} DKP користувачу {receiver.mention}!",
            allowed_mentions=discord.AllowedMentions(users=True))


class DKPView(discord.ui.View):
    def __init__(self, members):
        super().__init__(timeout=None)
        self.add_item(DKPDropdown(members))
        self.add_item(discord.ui.Button(label="Передати", style=discord.ButtonStyle.green, custom_id="transfer_button"))

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.data and interaction.data.get("custom_id") == "transfer_button":
        await interaction.response.send_modal(DKPTransferModal(interaction.user.id, None))

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

        # Trade DKP
        global pinned_message_id
        print(f'Logged in as {bot.user}')
        channel = bot.get_channel(TRANSFER_CHANNEL_ID)

        if not channel:
            print("Invalid channel ID")
            return

        pinned_message_id = load_trade_pinned_message_id()

        members = [member for member in channel.guild.members if
                   any(role.name == MEMBER_ROLE for role in member.roles)]
        view = DKPView(members)
        message_content = "Тут ви можете передати свої DKP іншій людині.\nВиберіть члена клану, кому ви б хотіли передати свої ДКП."

        if pinned_message_id:
            msg = await channel.fetch_message(pinned_message_id)
            await msg.edit(content=message_content, view=view)
        else:
            msg = await channel.send(content=message_content, view=view)
            await msg.pin()
            pinned_message_id = msg.id
            save_trade_pinned_message_id(pinned_message_id)
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")

async def setup():
    await bot.add_cog(DKPManager(bot))
    logger.info("DKPManager cog has been loaded.")

bot.run(DISCORD_TOKEN)
