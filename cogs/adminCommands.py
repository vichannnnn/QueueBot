from discord.ext import commands
from discord.ext.commands import has_permissions
import cogs.colourEmbed as functions
import traceback
import sqlite3
import discord

conn = sqlite3.connect('bot.db', timeout=5.0)
c = conn.cursor()
conn.row_factory = sqlite3.Row

c.execute(
    '''CREATE TABLE IF NOT EXISTS serverSettings (
    `serverID` INT, 
    `queueTitle` TEXT, 
    `description` TEXT,
    `channelID` INT, 
    `boardID` INT,
    UNIQUE(serverID, channelID)
    )''')


c.execute(
    '''CREATE TABLE IF NOT EXISTS queueBoard (
    `serverID` INT, 
    `queueName` TEXT,
    `voiceID` INT,
    UNIQUE(serverID, queueName)
    ) ''')

c.execute(
    '''CREATE TABLE IF NOT EXISTS queue (
    `userID` INT PRIMARY KEY, 
    `purpose` TEXT DEFAULT "",
    `voiceID` INT
    ) ''')

async def boardUpdate(self, guild):
    serverProperties = [i for i in c.execute('SELECT * FROM serverSettings WHERE serverID = ? ', (guild, ))]

    if serverProperties:
        ID, title, description, channelID, boardID = serverProperties[0]

        channelObject = self.bot.get_channel(channelID)
        guildObject = self.bot.get_guild(guild)
        msg = await channelObject.fetch_message(boardID)
        description = f"{description}\n\n"

        queueList = [i for i in c.execute('SELECT queueName, voiceID FROM queueBoard WHERE serverID = ? ORDER BY rowid ', (guild, ))]

        if queueList:
            for queueName, voiceID in queueList:
                description += f"**{queueName}**\n"
                userQueues = [i for i in c.execute('SELECT userID, purpose FROM queue WHERE voiceID = ? ', (voiceID, ))]
                if userQueues:
                    i = 1
                    for userID, purpose in userQueues:
                        if not purpose:
                            description += f"{i}. {guildObject.get_member(userID).mention}\n"
                        else:
                            description += f"{i}. {guildObject.get_member(userID).mention} - `{purpose}`\n"
                        i += 1
                description += "\n"

        embed = discord.Embed(title=title, description=description, colour=functions.embedColour(guild))
        await msg.edit(embed=embed)

class AdminCommands(commands.Cog, name="🛠️ Admin Commands"):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):

        if member.bot:
            return

        queues = [i for i in c.execute('SELECT * FROM queueBoard WHERE serverID = ? ', (member.guild.id, ))]
        channelList = [i[2] for i in queues]
        memberList = [i[0] for i in c.execute('SELECT userID FROM queue')]

        if not member.voice: # If they left
            if member.id in memberList:  # If they are in the list
                c.execute('DELETE FROM queue WHERE userID = ? ', (member.id,))
                conn.commit()
                await boardUpdate(self, member.guild.id)
                return
            return

        if member.voice.channel.id in channelList: # If they are in the queue
            if member.id in memberList:  # If they are not in the list
                c.execute('INSERT OR REPLACE INTO queue (userID, voiceID) VALUES (?, ?)', (member.id, member.voice.channel.id))
                conn.commit()
                await boardUpdate(self, member.guild.id)
                return

        if member.voice.channel.id not in channelList: # If heir current channel not in queue
            if member.id in memberList: # If they are in the list
                c.execute('DELETE FROM queue WHERE userID = ? ', (member.id,))
                conn.commit()
                await boardUpdate(self, member.guild.id)
                return

        if member.voice.channel.id in channelList: # If they are in the queue
            if member.id not in memberList:  # If they are not in the list
                c.execute('INSERT INTO queue (userID, voiceID) VALUES (?, ?)', (member.id, member.voice.channel.id))
                conn.commit()
                await boardUpdate(self, member.guild.id)
                return

    @commands.command(description=f"deletequeue [Queue Name]**\n\nDeletes the queue in the server.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    @has_permissions(administrator=True)
    async def deletequeue(self, ctx, *, queueName):

        c.execute('DELETE FROM queueBoard WHERE serverID = ? AND queueName = ? ', (ctx.guild.id, queueName))
        conn.commit()
        await boardUpdate(self, ctx.guild.id)
        return await functions.successEmbedTemplate(ctx, f"Successfully deleted the queue **{queueName}**.",
                                                    ctx.author)

    @commands.command(description=f"deleteboard**\n\nDeletes the queue display board in the server.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    @has_permissions(administrator=True)
    async def deleteboard(self, ctx):

        serverProperties = [i for i in c.execute('SELECT * FROM serverSettings WHERE serverID = ? ', (ctx.guild.id,))]
        if serverProperties:

            ID, title, description, channelID, boardID = serverProperties[0]
            channelObject = self.bot.get_channel(channelID)
            msg = await channelObject.fetch_message(boardID)
            await msg.delete()

        c.execute('DELETE FROM queueBoard WHERE serverID = ? ', (ctx.guild.id, ))
        conn.commit()
        return await functions.successEmbedTemplate(ctx, f"Successfully deleted the queue board in this server.", ctx.author)


    @commands.command(description=f"setboard**\n\nSets a queue display board in the server.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    @has_permissions(administrator=True)
    async def setboard(self, ctx):

        await ctx.send("Please mention the text channel you'd like to set the board in.")

        def check(m):
            return m.channel == ctx.message.channel and m.author == ctx.message.author

        channel = await self.bot.wait_for('message', check=check, timeout=30)
        channelList = [i.id for i in ctx.guild.channels]
        channelID = channel.content.replace('<', '').replace('>', '').replace('#', '')

        while int(channelID) not in channelList:
            await functions.errorEmbedTemplate(ctx, f"Invalid input. Please mention the channel again.", ctx.author)
            channelID = await self.bot.wait_for('message', check=check)

        await ctx.send("Please enter the title of the board.")
        title = await self.bot.wait_for('message', check=check, timeout=30)

        await ctx.send("Please enter the description of the board.")
        description = await self.bot.wait_for('message', check=check, timeout=30)

        channelObject = self.bot.get_channel(int(channelID))
        embed = discord.Embed(title=title.content, description=description.content, colour=functions.embedColour(ctx.guild.id))
        msg = await channelObject.send(embed=embed)

        c.execute('INSERT OR REPLACE INTO serverSettings VALUES (?, ?, ?, ?, ?) ',
                  (ctx.guild.id, title.content, description.content, int(channelID), msg.id))
        conn.commit()
        await boardUpdate(self, ctx.guild.id)
        await ctx.send(f"Successfully set up the queue board in {channelObject.mention}")


    @commands.command(description=f"setqueue**\n\nDesignates a voice room as a queue.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    @has_permissions(administrator=True)
    async def setqueue(self, ctx):

        await ctx.send("Please enter the voice channel ID you'd like to set as the queue.")

        def check(m):
            return m.channel == ctx.message.channel and m.author == ctx.message.author

        voiceID = await self.bot.wait_for('message', check=check, timeout=30)
        voiceList = [i.id for i in ctx.guild.voice_channels]

        while not voiceID.content.isdigit() or int(voiceID.content) not in voiceList:
            await functions.errorEmbedTemplate(ctx, f"The voice channel ID you've entered does not exist.\n"
                                                    f"Please enter the voice channel ID again.", ctx.author)
            voiceID = await self.bot.wait_for('message', check=check)

        await ctx.send("Please enter the name of the queue you would like to create.")

        queueName = await self.bot.wait_for('message', check=check, timeout=30)
        nameList = [i[0] for i in c.execute('SELECT queueName FROM queueBoard WHERE serverID = ? ', (ctx.guild.id, ))]

        while queueName.content in nameList:
            await functions.errorEmbedTemplate(ctx, f"The queue name you're trying to create already exists.\n"
                                                    f"Please enter another queue name", ctx.author)
            queueName = await self.bot.wait_for('message', check=check, timeout=30)


        c.execute('INSERT INTO queueBoard VALUES (?, ?, ?)', (ctx.guild.id, queueName.content, int(voiceID.content)))
        conn.commit()
        await boardUpdate(self, ctx.guild.id)
        await ctx.send(f"Successfully created queue **{queueName.content}** for {self.bot.get_channel(int(voiceID.content)).mention}")


    @commands.command(description=f"embedsettings [colour code e.g. 0xffff0]**\n\nChanges the colour of the embed.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    @has_permissions(administrator=True)
    async def embedsettings(self, ctx, colour):

        try:
            await functions.colourChange(ctx, colour)

        except ValueError:
            traceback.print_exc()


def setup(bot):
    bot.add_cog(AdminCommands(bot))
