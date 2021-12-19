import discord
import os
import logging
import re

GUILD_ID = int(os.environ.get('GUILD_ID'))
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN')
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'ERROR')

intents = discord.Intents.all()
intents.members = True

client = discord.Client(intents=intents)

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)


async def operation(command, ammount, user_id):
    logger.info('operation started')
    for guild in client.guilds:
        if guild.id == GUILD_ID:
            logger.info('guild found')
            for member in guild.members:
                if member.id == user_id:
                    logger.info('user found')

                    res = re.search('^(.*)\[(.*)\]$', member.nick)
                    nick = res.group(1) if res else member.nick
                    value = int(res.group(2)) if res else 0

                    if command == 'minus':
                        ammount = ammount * -1

                    diff = value + ammount

                    await member.edit(nick=f'{nick}[{diff}]')


@client.event
async def on_ready():
    logger.info('We have logged in as {0.user}'.format(client))


@client.event
async def on_message(message):
    res = re.search('!(.*) <@!(.*)> (.*)', message.content)

    if message.author == client.user:
        return

    if message.content.startswith('!help'):
        await message.channel.send('Commands:\n`!plus|minus <nick> <ammount>`')
        return

    if not res:
        return

    command = res.group(1)
    user_id = int(res.group(2))
    ammount = int(res.group(3))

    if command in ('plus', 'minus'):
        logger.info(f'command: {command}, user: {user_id}, ammount: {ammount}')
        await operation(command, ammount, user_id)

client.run(DISCORD_TOKEN)
