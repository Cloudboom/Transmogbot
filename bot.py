import discord
from discord.ext import commands
import aiosqlite
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
import json
import os
from pathlib import Path
from pytz import timezone
import logging

# Load .env defaults without overriding vars provided by Docker/Compose.
load_dotenv(override=False)
channel_id=int(os.getenv('CHANNEL_ID'))
bot_token=os.getenv('BOT_TOKEN')
cron_schedule=os.getenv('CRON_SCHEDULE', '0 5 * * 3')
crontz = os.getenv('CRON_TZ', 'UTC')
db_path = os.getenv('DB_PATH', '/main.sqlite')
language_code = os.getenv('LANGUAGE', 'en')

LANGUAGE_DIR = Path(__file__).resolve().parent / "languages"


def _read_language_file(code):
    path = LANGUAGE_DIR / f"{code}.json"
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _resolve_language(code):
    requested = (code or "en").strip().lower().replace("_", "-")
    default_messages = _read_language_file("en")

    candidates = [requested]
    if "-" in requested:
        candidates.append(requested.split("-")[0])
    candidates.append("en")

    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        messages = _read_language_file(candidate)
        if messages:
            return candidate, messages, default_messages

    if default_messages:
        return "en", default_messages, default_messages
    return requested, {}, {}


active_language, language_messages, default_messages = _resolve_language(language_code)


def _lookup_message(messages, key):
    if not isinstance(messages, dict):
        return None

    direct = messages.get(key)
    if isinstance(direct, str):
        return direct

    node = messages
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]

    return node if isinstance(node, str) else None


def t(key, **kwargs):
    template = _lookup_message(language_messages, key) or _lookup_message(default_messages, key) or key
    try:
        return template.format(**kwargs)
    except Exception:
        return template

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logging.getLogger("apscheduler").setLevel(logging.INFO)
logging.info(t("log.cron_config", schedule=cron_schedule, tz=crontz, db=db_path))
logging.info(t("log.language_loaded", language=active_language, directory=LANGUAGE_DIR))

# Create the intents and activate the needed ones.
intents = discord.Intents.default()
intents.message_content = True 
intents.messages = True

bot = commands.Bot(command_prefix = '!', intents=intents)

#Output
async def cronjob():
    logging.info(t("log.cron_running"))
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

                    embed = discord.Embed(title=t("embed.dresscode_title"), color=discord.Color.purple())
                    embed.add_field(name=t("embed.next_theme"), value=result, inline=False)
                    embed.add_field(name=t("embed.submitted_by"), value=user, inline=False)
                    embed.add_field(name=t("embed.themes_count"), value=count, inline=False)
                    await bot.change_presence(activity=discord.Game(name=t("presence.theme", theme=result)))
                    await channel.send(f"{mentions}", embed=embed)
                else:
                    embed = discord.Embed(title=t("embed.dresscode_title"), color=discord.Color.purple())
                    embed.add_field(name=t("embed.next_theme"), value=t("embed.no_themes_available"), inline=False)
                    await bot.change_presence(activity=discord.Game(name=t("presence.no_themes")))
                    await channel.send(embed=embed)
    except Exception as e:
        logging.error(t("log.cron_error", error=e))

# Scheduler creation
scheduler = AsyncIOScheduler(
    timezone=timezone(crontz),  # use env var here
    job_defaults={"coalesce": True, "max_instances": 1}
)

def register_jobs_once():
    trigger = CronTrigger.from_crontab(cron_schedule, timezone=timezone(crontz))

    scheduler.add_job(
        cronjob,
        trigger,
        id="weekly_motto_job",
        replace_existing=True
)

#Server startup
@bot.event
async def on_ready():
    if getattr(bot, "_ready_once", False):
        return
    bot._ready_once = True
    logging.info(t("log.bot_ready", user=bot.user, user_id=bot.user.id))
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
        logging.info(t("log.awake"))
        register_jobs_once()
        if not scheduler.running:
            scheduler.start()
            logging.info(t("log.scheduler_started"))
    except Exception as e:
        logging.error(t("log.db_init_error", error=e))

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
                await ctx.send(
                    t("msg.tmnew_success", user=ctx.message.author.global_name, theme=arg),
                    delete_after=60
                )
            else:
                await ctx.send(
                    t("msg.tmnew_duplicate", user=ctx.message.author.global_name, theme=arg),
                    delete_after=60
                )
        await ctx.message.delete()
    except Exception as e:
        await ctx.send(t("msg.tmnew_error", error=e))

@tmnew.error 
async def tmnew_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(t("msg.tmnew_missing_arg"))

#Delete messages in chat
@bot.command()
async def tmdelete(ctx, limit: int = None):
    try: 
        async for msg in ctx.message.channel.history(limit=limit):
            await msg.delete()
        logging.info(t("log.messages_cleared"))
    except Exception as e:
        logging.error(t("log.delete_error", error=e))

#List themes for user
@bot.command()
async def tmuser(ctx):
    try:
        channel = bot.get_channel(channel_id)
        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT user, COUNT(theme) FROM themes WHERE state = 'unused' GROUP BY user") as cursor:
                result = await cursor.fetchall()
        embed = discord.Embed(title=t("embed.user_count_title"), color=discord.Color.green())
        for user, count in result:
            embed.add_field(name=user, value=str(count), inline=False)
        await channel.send(embed=embed)
        await ctx.message.delete()
    except Exception as e:
        await ctx.send(t("msg.tmuser_error", error=e))

#List all themes
@bot.command(name='tmall')
async def tmall(ctx):
    try:
        channel = bot.get_channel(channel_id)
        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT user, theme FROM themes WHERE state = 'unused'") as cursor:
                result = await cursor.fetchall()
        embed = discord.Embed(title=t("embed.all_themes_title"), color=discord.Color.gold())
        for user, theme in result:
            embed.add_field(name=user, value=theme, inline=False)
        await channel.send(embed=embed)
        await ctx.message.delete()
    except Exception as e:
        await ctx.send(t("msg.tmall_error", error=e))

#Turn output on
@bot.command(name='tmon')
async def tmon(ctx):
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("UPDATE settings SET output_active = 1")
            await db.commit()
            await ctx.send(t("msg.tmon_success"))
            
    except Exception as e:
        await ctx.send(t("msg.tmon_error", error=e))

#Turn output off
@bot.command(name='tmoff')
async def tmoff(ctx):
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("UPDATE settings SET output_active = 0")
            await db.commit()
            await ctx.send(t("msg.tmoff_success"))
            
    except Exception as e:
        await ctx.send(t("msg.tmoff_error", error=e))

#Add user to notification
@bot.command(name='tmnotify')
async def tmnotify(ctx):
    try:
        logging.info(t("log.notify_subscribe", user=ctx.message.author.global_name))
        async with aiosqlite.connect(db_path) as db:
            await db.execute("INSERT OR REPLACE INTO notification (user) VALUES (?)", (ctx.message.author.id,))
            await db.commit()
            await ctx.send(t("msg.tmnotify_success"))
            
    except Exception as e:
        await ctx.send(t("msg.tmnotify_error", error=e))

#Remove user from notification
@bot.command(name='tmnotifyoff')
async def tmnotifyoff(ctx):
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("DELETE FROM notification WHERE user = ?", (ctx.message.author.id,))
            await db.commit()
            await ctx.send(t("msg.tmnotifyoff_success"))
            
    except Exception as e:
        await ctx.send(t("msg.tmnotifyoff_error", error=e))

#Help
@bot.command()    
async def tmhelp(ctx):
    try:    
        await ctx.send(t("help.line1"))
        await ctx.send(t("help.line2"))
        await ctx.send(t("help.line3"))
        await ctx.send(t("help.line4"))
        await ctx.send(t("help.line5"))
        await ctx.message.delete()
    except Exception as e:
        await ctx.send(t("msg.tmhelp_error", error=e))

bot.run(bot_token)
