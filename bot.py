import discord
from discord import app_commands
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
LANGUAGE_CACHE = {}


def _normalize_language_code(code):
    if code is None:
        return None
    value = getattr(code, "value", code)
    normalized = str(value).strip().lower().replace("_", "-")
    return normalized or None


def _read_language_file(code):
    normalized = _normalize_language_code(code)
    if not normalized:
        return {}
    if normalized in LANGUAGE_CACHE:
        return LANGUAGE_CACHE[normalized]

    path = LANGUAGE_DIR / f"{normalized}.json"
    if not path.exists():
        LANGUAGE_CACHE[normalized] = {}
        return {}
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        LANGUAGE_CACHE[normalized] = data if isinstance(data, dict) else {}
        return LANGUAGE_CACHE[normalized]
    except Exception:
        LANGUAGE_CACHE[normalized] = {}
        return {}


def _resolve_language(code):
    requested = _normalize_language_code(code) or "en"
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


def _translate_with_fallback(key, candidate_codes, **kwargs):
    template = None
    seen = set()

    for code in candidate_codes:
        normalized = _normalize_language_code(code)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)

        template = _lookup_message(_read_language_file(normalized), key)
        if template:
            break

        if "-" in normalized:
            base = normalized.split("-")[0]
            if base not in seen:
                seen.add(base)
                template = _lookup_message(_read_language_file(base), key)
                if template:
                    break

    if not template:
        template = _lookup_message(default_messages, key) or key

    try:
        return template.format(**kwargs)
    except Exception:
        return template


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


def ti(interaction, key, **kwargs):
    return _translate_with_fallback(
        key,
        [
            getattr(interaction, "locale", None),
            getattr(interaction, "guild_locale", None),
            "en",
        ],
        **kwargs,
    )


def get_user_name(user):
    return getattr(user, "global_name", None) or getattr(user, "display_name", None) or str(user)


class JsonCommandTranslator(app_commands.Translator):
    async def translate(self, string, locale, context):
        if not isinstance(string, app_commands.locale_str):
            return None

        key = string.extras.get("key")
        if not key:
            return None

        return _translate_with_fallback(key, [locale, "en"])


async def send_interaction_message(interaction, *, content=None, embed=None, ephemeral=False):
    if interaction.response.is_done():
        await interaction.followup.send(content=content, embed=embed, ephemeral=ephemeral)
    else:
        await interaction.response.send_message(content=content, embed=embed, ephemeral=ephemeral)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logging.getLogger("apscheduler").setLevel(logging.INFO)
logging.info(t("log.cron_config", schedule=cron_schedule, tz=crontz, db=db_path))
logging.info(t("log.language_loaded", language=active_language, directory=LANGUAGE_DIR))

# Create the intents and activate the needed ones.
intents = discord.Intents.default()
intents.messages = True

bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)
command_translator = JsonCommandTranslator()

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
        try:
            await bot.tree.set_translator(command_translator)
            synced = await bot.tree.sync()
            logging.info(t("log.commands_synced", count=len(synced)))
        except Exception as e:
            logging.error(t("log.commands_sync_error", error=e))
    except Exception as e:
        logging.error(t("log.db_init_error", error=e))

#Adding new event
@bot.tree.command(
    name='tmnew',
    description=app_commands.locale_str("Submit a new theme.", key="cmd.tmnew.description")
)
@app_commands.describe(arg=app_commands.locale_str("Theme to submit", key="cmd.tmnew.arg"))
async def tmnew(interaction: discord.Interaction, arg: str):
    try:
        author_name = get_user_name(interaction.user)
        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT theme FROM themes WHERE theme = ?", (arg,)) as cursor:
                result = await cursor.fetchone()
            if result is None:
                await db.execute("INSERT INTO themes(state, theme, user) VALUES ('unused', ?, ?)", (arg, author_name))
                await db.commit()
                await send_interaction_message(interaction, content=ti(interaction, "msg.tmnew_success", user=author_name, theme=arg))
            else:
                await send_interaction_message(interaction, content=ti(interaction, "msg.tmnew_duplicate", user=author_name, theme=arg))
    except Exception as e:
        await send_interaction_message(interaction, content=ti(interaction, "msg.tmnew_error", error=e), ephemeral=True)


#Delete messages in chat
@bot.tree.command(
    name='tmdelete',
    description=app_commands.locale_str("Delete recent messages in the current channel.", key="cmd.tmdelete.description")
)
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(limit=app_commands.locale_str("How many recent messages to delete", key="cmd.tmdelete.limit"))
async def tmdelete(interaction: discord.Interaction, limit: int = 100):
    try:
        channel = interaction.channel
        if channel is None:
            await send_interaction_message(interaction, content=ti(interaction, "msg.tmdelete_no_channel"), ephemeral=True)
            return

        deleted_count = 0
        async for msg in channel.history(limit=limit):
            await msg.delete()
            deleted_count += 1

        logging.info(t("log.messages_cleared"))
        await send_interaction_message(
            interaction,
            content=ti(interaction, "msg.tmdelete_success", count=deleted_count),
            ephemeral=True
        )
    except Exception as e:
        logging.error(t("log.delete_error", error=e))
        await send_interaction_message(interaction, content=ti(interaction, "msg.tmdelete_error", error=e), ephemeral=True)


@tmdelete.error
async def tmdelete_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await send_interaction_message(interaction, content=ti(interaction, "msg.tmdelete_admin_only"), ephemeral=True)
        return
    if isinstance(error, app_commands.NoPrivateMessage):
        await send_interaction_message(interaction, content=ti(interaction, "msg.tmdelete_no_dm"), ephemeral=True)
        return

    logging.error(t("log.delete_error", error=error))
    await send_interaction_message(interaction, content=ti(interaction, "msg.tmdelete_error", error=error), ephemeral=True)


#List themes for user
@bot.tree.command(
    name='tmuser',
    description=app_commands.locale_str("Show count of submitted themes per user.", key="cmd.tmuser.description")
)
async def tmuser(interaction: discord.Interaction):
    try:
        target_channel = bot.get_channel(channel_id) or interaction.channel
        if target_channel is None:
            await send_interaction_message(interaction, content=ti(interaction, "msg.target_channel_missing"), ephemeral=True)
            return

        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT user, COUNT(theme) FROM themes WHERE state = 'unused' GROUP BY user") as cursor:
                result = await cursor.fetchall()
        embed = discord.Embed(title=ti(interaction, "embed.user_count_title"), color=discord.Color.green())
        for user, count in result:
            embed.add_field(name=user, value=str(count), inline=False)

        await target_channel.send(embed=embed)
        await send_interaction_message(interaction, content=ti(interaction, "msg.sent_to_channel"), ephemeral=True)
    except Exception as e:
        await send_interaction_message(interaction, content=ti(interaction, "msg.tmuser_error", error=e), ephemeral=True)


#List all themes
@bot.tree.command(
    name='tmall',
    description=app_commands.locale_str("List all currently unused themes.", key="cmd.tmall.description")
)
async def tmall(interaction: discord.Interaction):
    try:
        target_channel = bot.get_channel(channel_id) or interaction.channel
        if target_channel is None:
            await send_interaction_message(interaction, content=ti(interaction, "msg.target_channel_missing"), ephemeral=True)
            return

        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT user, theme FROM themes WHERE state = 'unused'") as cursor:
                result = await cursor.fetchall()
        embed = discord.Embed(title=ti(interaction, "embed.all_themes_title"), color=discord.Color.gold())
        for user, theme in result:
            embed.add_field(name=user, value=theme, inline=False)

        await target_channel.send(embed=embed)
        await send_interaction_message(interaction, content=ti(interaction, "msg.sent_to_channel"), ephemeral=True)
    except Exception as e:
        await send_interaction_message(interaction, content=ti(interaction, "msg.tmall_error", error=e), ephemeral=True)


#Turn output on
@bot.tree.command(
    name='tmon',
    description=app_commands.locale_str("Enable scheduled output posting.", key="cmd.tmon.description")
)
async def tmon(interaction: discord.Interaction):
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("UPDATE settings SET output_active = 1")
            await db.commit()
            await send_interaction_message(interaction, content=ti(interaction, "msg.tmon_success"))
    except Exception as e:
        await send_interaction_message(interaction, content=ti(interaction, "msg.tmon_error", error=e), ephemeral=True)


#Turn output off
@bot.tree.command(
    name='tmoff',
    description=app_commands.locale_str("Disable scheduled output posting.", key="cmd.tmoff.description")
)
async def tmoff(interaction: discord.Interaction):
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("UPDATE settings SET output_active = 0")
            await db.commit()
            await send_interaction_message(interaction, content=ti(interaction, "msg.tmoff_success"))
    except Exception as e:
        await send_interaction_message(interaction, content=ti(interaction, "msg.tmoff_error", error=e), ephemeral=True)


#Add user to notification
@bot.tree.command(
    name='tmnotify',
    description=app_commands.locale_str("Enable notifications for the current user.", key="cmd.tmnotify.description")
)
async def tmnotify(interaction: discord.Interaction):
    try:
        logging.info(t("log.notify_subscribe", user=get_user_name(interaction.user)))
        async with aiosqlite.connect(db_path) as db:
            await db.execute("INSERT OR REPLACE INTO notification (user) VALUES (?)", (interaction.user.id,))
            await db.commit()
            await send_interaction_message(interaction, content=ti(interaction, "msg.tmnotify_success"))
    except Exception as e:
        await send_interaction_message(interaction, content=ti(interaction, "msg.tmnotify_error", error=e), ephemeral=True)


#Remove user from notification
@bot.tree.command(
    name='tmnotifyoff',
    description=app_commands.locale_str("Disable notifications for the current user.", key="cmd.tmnotifyoff.description")
)
async def tmnotifyoff(interaction: discord.Interaction):
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("DELETE FROM notification WHERE user = ?", (interaction.user.id,))
            await db.commit()
            await send_interaction_message(interaction, content=ti(interaction, "msg.tmnotifyoff_success"))
    except Exception as e:
        await send_interaction_message(interaction, content=ti(interaction, "msg.tmnotifyoff_error", error=e), ephemeral=True)


#Help
@bot.tree.command(
    name='tmhelp',
    description=app_commands.locale_str("Show available bot commands.", key="cmd.tmhelp.description")
)
async def tmhelp(interaction: discord.Interaction):
    try:
        help_text = "\n".join([
            ti(interaction, "help.line1"),
            ti(interaction, "help.line2"),
            ti(interaction, "help.line3"),
            ti(interaction, "help.line4"),
            ti(interaction, "help.line5")
        ])
        await send_interaction_message(interaction, content=help_text, ephemeral=True)
    except Exception as e:
        await send_interaction_message(interaction, content=ti(interaction, "msg.tmhelp_error", error=e), ephemeral=True)

bot.run(bot_token)
