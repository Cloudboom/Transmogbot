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
channel_id=os.getenv('CHANNEL_ID')
bot_token=os.getenv('BOT_TOKEN')

# Erstelle die Intents und aktiviere die benötigten
intents = discord.Intents.default()
intents.message_content = True  # Aktivieren des Zugriffs auf den Nachrichteninhalt
intents.messages = True  # Aktivieren des Zugriffs auf Nachrichtenereignisse

bot = commands.Bot(command_prefix = '!', intents=intents)

#Ausgeben anfang
async def cronjob():
    print("Cron-Job wird ausgeführt")  # Debug-Ausgabe, um sicherzustellen, dass der Cron-Job gestartet wird
    try:
        channel = bot.get_channel(channel_id)
        async with aiosqlite.connect('main.sqlite') as db:
            async with db.execute("SELECT theme FROM main WHERE state = 'unused' ORDER BY RANDOM() LIMIT 1") as cursor:
                result = await cursor.fetchone()
            if result:
                result = result[0]
                async with db.execute("SELECT user FROM main WHERE theme = ?", (result,)) as cursor:
                    user = await cursor.fetchone()
                user = user[0]
                await db.execute("UPDATE main SET state = 'used' WHERE theme = ?", (result,))
                await db.commit()
                async with db.execute("SELECT COUNT(theme) FROM main WHERE state = 'unused'") as cursor:
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
        print(f"Fehler beim Ausführen des Cronjobs: {e}")

# Scheduler erstellen und konfigurieren
scheduler = AsyncIOScheduler()
scheduler.add_job(cronjob, CronTrigger(day_of_week='wed', hour=5, minute=0))
#Ausgeben ende

@bot.event
async def on_ready():
    print(f'Wir haben uns als {bot.user} eingeloggt')
    try:
        async with aiosqlite.connect('main.sqlite') as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS main(
	                state TEXT,
	                theme TEXT,
                    user TEXT
                )
            ''')
            await db.commit()
        print('Ich bin wach.')
#        scheduler.start()
    except Exception as e:
        print(f"Fehler beim Initialisieren der Datenbank: {e}")

#Einreichen anfang
@bot.command(pass_context=True)    
async def tmnew(ctx, *, arg):
    try:
        async with aiosqlite.connect('main.sqlite') as db:
            async with db.execute("SELECT theme FROM main WHERE theme = ?", (arg,)) as cursor:
                result = await cursor.fetchone()
            if result is None:
                await db.execute("INSERT INTO main(state, theme, user) VALUES ('unused', ?, ?)", (arg, ctx.message.author.name))
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
#Einreichen ende

#Löschen anfang
@bot.command()
async def tmdelete(ctx, limit: int = None):
    try: 
        channel = bot.get_channel(channel_id)
        async for msg in ctx.message.channel.history(limit=limit):
            await msg.delete()
        print(f"Cleared")
    except Exception as e:
        print(f"Fehler beim Löschen der Nachrichten: {e}")    
#Löschen Ende

#Mottos pro User
@bot.command()
async def tmuser(ctx):
    try:
        channel = bot.get_channel(channel_id)
        async with aiosqlite.connect('main.sqlite') as db:
            async with db.execute("SELECT user, COUNT(theme) FROM main WHERE state = 'unused' GROUP BY user") as cursor:
                result = await cursor.fetchall()
        embed = discord.Embed(title="Wer hat wie viel eingereicht", color=discord.Color.green())
        for user, count in result:
            embed.add_field(name=user, value=str(count), inline=False)
        await channel.send(embed=embed)
        await ctx.message.delete()
    except Exception as e:
        await ctx.send(f"Fehler beim Abrufen der Benutzerdaten: {e}")
#Mottos pro User ende

#Mottos
@bot.command(name='tmall')
async def tmall(ctx):
    try:
        channel = bot.get_channel(channel_id)
        async with aiosqlite.connect('main.sqlite') as db:
            async with db.execute("SELECT user, theme FROM main WHERE state = 'unused'") as cursor:
                result = await cursor.fetchall()
        embed = discord.Embed(title="Wer hat was eingereicht", color=discord.Color.gold())
        for user, theme in result:
            embed.add_field(name=user, value=theme, inline=False)
        await channel.send(embed=embed)
        await ctx.message.delete()
    except Exception as e:
        await ctx.send(f"Fehler beim Abrufen der Mottos: {e}")
#Ende Mottos

#Help anfang
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
#Help ende

bot.run(bot_token)

