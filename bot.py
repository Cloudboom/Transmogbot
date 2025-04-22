import discord
from discord.ext import commands
import aiosqlite
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio
from dotenv import load_dotenv
import os

# Load the environment variables from the .env file
load_dotenv()
channel_id=int(os.getenv('CHANNEL_ID'))
bot_token=os.getenv('BOT_TOKEN')
cronweek=os.getenv('CRON_DAY_OF_WEEK')
cronhour=os.getenv('CRON_HOUR')
cronminute=os.getenv('CRON_MINUTE')

# Create the intents and activate the needed ones.
intents = discord.Intents.default()
intents.message_content = True 
intents.messages = True

bot = commands.Bot(command_prefix = '!', intents=intents)

#Output
async def cronjob():
    print("Cron-Job is running.") 
    try:
        channel = bot.get_channel(channel_id)
        async with aiosqlite.connect('main.sqlite') as db:
            async with db.execute("SELECT output_active FROM settings") as cursor:
                setting = await cursor.fetchone()

            if setting and setting[0] == 1:    
                async with db.execute("SELECT theme FROM events WHERE state = 'unused' ORDER BY RANDOM() LIMIT 1") as cursor:
                    result = await cursor.fetchone()
                if result:
                    result = result[0]
                    async with db.execute("SELECT user FROM events WHERE theme = ?", (result,)) as cursor:
                        user = await cursor.fetchone()
                    user = user[0]
                    await db.execute("UPDATE events SET state = 'used' WHERE theme = ?", (result,))
                    await db.commit()
                    async with db.execute("SELECT COUNT(theme) FROM events WHERE state = 'unused'") as cursor:
                        count = await cursor.fetchone()
                    count = count[0]

                    embed = discord.Embed(title="Dresscode am Sonntag", color=discord.Color.purple())
                    embed.add_field(name="Nächstes Motto", value=result, inline=False)
                    embed.add_field(name="Eingereicht von", value=user, inline=False)
                    embed.add_field(name="Mottos in Hashoms Kiste", value=count, inline=False)
                    await bot.change_presence(activity=discord.Game(name=f"Motto: {result}"))
                    await channel.send(embed=embed)
                else:
                    embed = discord.Embed(title="Dresscode am Sonntag", color=discord.Color.purple())
                    embed.add_field(name="Nächstes Motto", value="Es tut mir leid Reisender, aktuell sind alle Mottos aufgebraucht.", inline=False)
                    await bot.change_presence(activity=discord.Game(name="Mottos aufgebraucht"))
                    await channel.send(embed=embed)
    except Exception as e:
        print(f"Error while running the cronjob: {e}")

# Scheduler creation
scheduler = AsyncIOScheduler()
scheduler.add_job(cronjob, CronTrigger(day_of_week=cronweek, hour=cronhour, minute=cronminute))

#Server startup
@bot.event
async def on_ready():
    print(f'Wir haben uns als {bot.user} eingeloggt')
    try:
        async with aiosqlite.connect('main.sqlite') as db:

            async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='main'") as cursor:
                table_exists = await cursor.fetchone()

            if table_exists:
                print("Renaming 'main' to 'events'...")
                await db.execute("ALTER TABLE main RENAME TO events")
            else:
                print("'main' does not exist or already renamed.")

            await db.execute('''
                CREATE TABLE IF NOT EXISTS events(
	                state TEXT,
	                theme TEXT,
                    user TEXT
                )
            ''')

            # Create the settings table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    output_active INTEGER
                )
            ''')

            # Insert default value if settings table is empty
            await db.execute('''
                INSERT INTO settings (output_active)
                SELECT 1
                WHERE NOT EXISTS (SELECT 1 FROM settings)
            ''')

            await db.commit()
        print('Im awake.')
        scheduler.start()
    except Exception as e:
        print(f"Error initializing the database: {e}")

#Adding new event
@bot.command(pass_context=True)    
async def tmnew(ctx, *, arg):
    try:
        async with aiosqlite.connect('main.sqlite') as db:
            async with db.execute("SELECT theme FROM events WHERE theme = ?", (arg,)) as cursor:
                result = await cursor.fetchone()
            if result is None:
                await db.execute("INSERT INTO events(state, theme, user) VALUES ('unused', ?, ?)", (arg, ctx.message.author.name))
                await db.commit()
                await ctx.send(f"{ctx.message.author.name} hat das Motto |{arg}| eingereicht.", delete_after=60)
            else:
                await ctx.send(f"Sorry {ctx.message.author.name}, das Motto wurde schon eingereicht.", delete_after=60)
        await ctx.message.delete()
    except Exception as e:
        await ctx.send(f"Fehler beim Einreichen des Mottos: {e}")    

@tmnew.error 
async def tmnew_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Bitte gib ein Motto mit an.")

#Delete messages in chat
@bot.command()
async def tmdelete(ctx, limit: int = None):
    try: 
        channel = bot.get_channel(channel_id)
        async for msg in ctx.message.channel.history(limit=limit):
            await msg.delete()
        print(f"Cleared")
    except Exception as e:
        print(f"Error on deleting messages: {e}")    

#List events for user
@bot.command()
async def tmuser(ctx):
    try:
        channel = bot.get_channel(channel_id)
        async with aiosqlite.connect('main.sqlite') as db:
            async with db.execute("SELECT user, COUNT(theme) FROM events WHERE state = 'unused' GROUP BY user") as cursor:
                result = await cursor.fetchall()
        embed = discord.Embed(title="Wer hat wie viel eingereicht", color=discord.Color.green())
        for user, count in result:
            embed.add_field(name=user, value=str(count), inline=False)
        await channel.send(embed=embed)
        await ctx.message.delete()
    except Exception as e:
        await ctx.send(f"Fehler beim Abrufen der Benutzerdaten: {e}")

#List all events
@bot.command(name='tmall')
async def tmall(ctx):
    try:
        channel = bot.get_channel(channel_id)
        async with aiosqlite.connect('main.sqlite') as db:
            async with db.execute("SELECT user, theme FROM events WHERE state = 'unused'") as cursor:
                result = await cursor.fetchall()
        embed = discord.Embed(title="Wer hat was eingereicht", color=discord.Color.gold())
        for user, theme in result:
            embed.add_field(name=user, value=theme, inline=False)
        await channel.send(embed=embed)
        await ctx.message.delete()
    except Exception as e:
        await ctx.send(f"Fehler beim Abrufen der Mottos: {e}")

# Turn outputt on
@bot.command(name='tmon')
async def tmon(ctx):
    try:
        channel = bot.get_channel(channel_id)
        async with aiosqlite.connect('main.sqlite') as db:
            await db.execute("UPDATE settings SET output_active = 1")
            await db.commit()
            await ctx.send("Ausgabe aktiviert.")
            
    except Exception as e:
        await ctx.send(f"Aktivieren fehlgeschlagen: {e}")   

# Turn outputt off
@bot.command(name='tmoff')
async def tmoff(ctx):
    try:
        channel = bot.get_channel(channel_id)
        async with aiosqlite.connect('main.sqlite') as db:
            await db.execute("UPDATE settings SET output_active = 0")
            await db.commit()
            await ctx.send("Ausgabe abgeschaltet.")
            
    except Exception as e:
        await ctx.send(f"Abschalten fehlgeschlagen: {e}")    

#Help
@bot.command()    
async def tmhelp(ctx):
    try:    
        await ctx.send("Du möchtest meine Hilfe?")
        await ctx.send("Mit z.B. `!tmnew |Name des Mottos| (ohne die Sonderzeichen))` kannst du etwas Neues einreichen.")
        await ctx.send("Mit `!tmuser` kannst du dir ausgeben lassen, wer wie viele Mottos eingereicht hat.")
        await ctx.send("Mit `!tmall` kannst du dir alle aktuellen Mottos auf der Liste ausgeben lassen.")
        await ctx.message.delete()
    except Exception as e:
        await ctx.send(f"Fehler beim Ausgeben der Hilfe: {e}")

bot.run(bot_token)

