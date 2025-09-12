import discord
from discord.ext import commands
import aiosqlite
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio
from dotenv import load_dotenv
import os
from pytz import timezone

# Load the environment variables from the .env file
load_dotenv()
channel_id=int(os.getenv('CHANNEL_ID'))
bot_token=os.getenv('BOT_TOKEN')
cronweek=os.getenv('CRON_DAY_OF_WEEK')
cronhour=os.getenv('CRON_HOUR')
cronminute=os.getenv('CRON_MINUTE')
crontz = os.getenv('CRON_TZ', 'UTC')
db_path = os.getenv("DB_PATH", "/main.sqlite")

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
        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT output_active FROM settings") as cursor:
                setting = await cursor.fetchone()

            if setting and setting[0] == 1:    
                async with db.execute("SELECT theme FROM themes WHERE state = 'unused' ORDER BY RANDOM() LIMIT 1") as cursor:
                    result = await cursor.fetchone()
                if result:
                    result = result[0]
                    async with db.execute("SELECT user FROM themes WHERE theme = ?", (result,)) as cursor:
                        user = await cursor.fetchone()
                    user = user[0]
                    await db.execute("UPDATE themes SET state = 'used' WHERE theme = ?", (result,))
                    await db.commit()
                    async with db.execute("SELECT COUNT(theme) FROM themes WHERE state = 'unused'") as cursor:
                        count = await cursor.fetchone()
                    count = count[0]

                    async with db.execute("SELECT user FROM notification") as cursor:
                        mention_users = await cursor.fetchall()
                    mentions = " ".join([f"<@{user[0]}>" for user in mention_users])  # Assuming 'user' is a Discord ID    

                    embed = discord.Embed(title="Dresscode am Sonntag", color=discord.Color.purple())
                    embed.add_field(name="Nächstes Motto", value=result, inline=False)
                    embed.add_field(name="Eingereicht von", value=user, inline=False)
                    embed.add_field(name="Mottos in Hashoms Kiste", value=count, inline=False)
                    await bot.change_presence(activity=discord.Game(name=f"Motto: {result}"))
                    await channel.send(f"{mentions}", embed=embed)
                else:
                    embed = discord.Embed(title="Dresscode am Sonntag", color=discord.Color.purple())
                    embed.add_field(name="Nächstes Motto", value="Es tut mir leid Reisender, aktuell sind alle Mottos aufgebraucht.", inline=False)
                    await bot.change_presence(activity=discord.Game(name="Mottos aufgebraucht"))
                    await channel.send(embed=embed)
    except Exception as e:
        print(f"Error while running the cronjob: {e}")

# Scheduler creation
scheduler = AsyncIOScheduler(
    timezone=timezone(crontz),  # use env var here
    job_defaults={"coalesce": True, "max_instances": 1}
)
scheduler.add_job(
    cronjob,
    CronTrigger(
        day_of_week=cronweek,
        hour=int(cronhour),
        minute=int(cronminute)
    ),
    id="weekly_motto_job",
    replace_existing=True
)

#Server startup
@bot.event
async def on_ready():
    print(f'Logged in as: {bot.user}')
    try:
        async with aiosqlite.connect(db_path) as db:

            await db.execute('''
                CREATE TABLE IF NOT EXISTS themes(
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

            await db.execute('''
                CREATE TABLE IF NOT EXISTS notification(
	                user TEXT PRIMARY KEY
                )
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
        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT theme FROM themes WHERE theme = ?", (arg,)) as cursor:
                result = await cursor.fetchone()
            if result is None:
                await db.execute("INSERT INTO themes(state, theme, user) VALUES ('unused', ?, ?)", (arg, ctx.message.author.global_name))
                await db.commit()
                await ctx.send(f"{ctx.message.author.global_name} hat das Motto |{arg}| eingereicht.", delete_after=60)
            else:
                await ctx.send(f"Sorry {ctx.message.author.global_name}, das Motto wurde schon eingereicht.", delete_after=60)
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

#List themes for user
@bot.command()
async def tmuser(ctx):
    try:
        channel = bot.get_channel(channel_id)
        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT user, COUNT(theme) FROM themes WHERE state = 'unused' GROUP BY user") as cursor:
                result = await cursor.fetchall()
        embed = discord.Embed(title="Wer hat wie viel eingereicht", color=discord.Color.green())
        for user, count in result:
            embed.add_field(name=user, value=str(count), inline=False)
        await channel.send(embed=embed)
        await ctx.message.delete()
    except Exception as e:
        await ctx.send(f"Fehler beim Abrufen der Benutzerdaten: {e}")

#List all themes
@bot.command(name='tmall')
async def tmall(ctx):
    try:
        channel = bot.get_channel(channel_id)
        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT user, theme FROM themes WHERE state = 'unused'") as cursor:
                result = await cursor.fetchall()
        embed = discord.Embed(title="Wer hat was eingereicht", color=discord.Color.gold())
        for user, theme in result:
            embed.add_field(name=user, value=theme, inline=False)
        await channel.send(embed=embed)
        await ctx.message.delete()
    except Exception as e:
        await ctx.send(f"Fehler beim Abrufen der Mottos: {e}")

#Turn output on
@bot.command(name='tmon')
async def tmon(ctx):
    try:
        channel = bot.get_channel(channel_id)
        async with aiosqlite.connect(db_path) as db:
            await db.execute("UPDATE settings SET output_active = 1")
            await db.commit()
            await ctx.send("Ausgabe aktiviert.")
            
    except Exception as e:
        await ctx.send(f"Aktivieren fehlgeschlagen: {e}")   

#Turn output off
@bot.command(name='tmoff')
async def tmoff(ctx):
    try:
        channel = bot.get_channel(channel_id)
        async with aiosqlite.connect(db_path) as db:
            await db.execute("UPDATE settings SET output_active = 0")
            await db.commit()
            await ctx.send("Ausgabe abgeschaltet.")
            
    except Exception as e:
        await ctx.send(f"Abschalten fehlgeschlagen: {e}")    

#Add user to notification
@bot.command(name='tmnotify')
async def tmnotify(ctx):
    try:
        print(ctx.message.author.global_name)
        channel = bot.get_channel(channel_id)
        async with aiosqlite.connect(db_path) as db:
            await db.execute("INSERT OR REPLACE INTO notification (user) VALUES (?)", (ctx.message.author.id,))
            await db.commit()
            await ctx.send("Benachrichtigung eingerichtet.")
            
    except Exception as e:
        await ctx.send(f"Einrichten fehlgeschlagen: {e}")   

#Remove user from notification
@bot.command(name='tmnotifyoff')
async def tmnotify(ctx):
    try:
        channel = bot.get_channel(channel_id)
        async with aiosqlite.connect(db_path) as db:
            await db.execute("DELETE FROM notification WHERE user = ?", (ctx.message.author.id,))
            await db.commit()
            await ctx.send("Benachrichtigung abgeschaltet.")
            
    except Exception as e:
        await ctx.send(f"Deaktivieren fehlgeschlagen: {e}")           

#Help
@bot.command()    
async def tmhelp(ctx):
    try:    
        await ctx.send("Du möchtest meine Hilfe?")
        await ctx.send("Mit z.B. `!tmnew |Name des Mottos| (ohne die Sonderzeichen))` kannst du etwas Neues einreichen.")
        await ctx.send("Mit `!tmuser` kannst du dir ausgeben lassen, wer wie viele Mottos eingereicht hat.")
        await ctx.send("Mit `!tmall` kannst du dir alle aktuellen Mottos auf der Liste ausgeben lassen.")
        await ctx.send("Mit `!tmnotify` kannst du dir eine Benachrichtugng einrichten.")
        await ctx.message.delete()
    except Exception as e:
        await ctx.send(f"Fehler beim Ausgeben der Hilfe: {e}")

bot.run(bot_token)