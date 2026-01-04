import os
import sqlite3
import datetime as dt

import discord
from discord import app_commands
from discord.ext import commands, tasks

TZ_OFFSET_HOURS = -6  # Costa Rica
DEFAULT_ANNOUNCE_HOUR = 9  # 9:00 am
DB_PATH = "birthdays.sqlite"

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
ANNOUNCE_CHANNEL_ID = int(os.getenv("ANNOUNCE_CHANNEL_ID", "0"))

if not DISCORD_TOKEN:
    raise RuntimeError("Falta DISCORD_TOKEN como variable de entorno.")
if ANNOUNCE_CHANNEL_ID == 0:
    raise RuntimeError("Falta ANNOUNCE_CHANNEL_ID como variable de entorno (ID del canal).")

def init_db():
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS birthdays (
            user_id INTEGER PRIMARY KEY,
            day INTEGER NOT NULL,
            month INTEGER NOT NULL
        );
        """)
        con.commit()

def set_birthday(user_id: int, day: int, month: int):
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT INTO birthdays(user_id, day, month) VALUES(?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET day=excluded.day, month=excluded.month;",
            (user_id, day, month),
        )
        con.commit()

def remove_birthday(user_id: int):
    with sqlite3.connect(DB_PATH) as con:
        con.execute("DELETE FROM birthdays WHERE user_id=?;", (user_id,))
        con.commit()

def list_birthdays():
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute("SELECT user_id, day, month FROM birthdays ORDER BY month, day;").fetchall()
    return rows

def birthdays_for(day: int, month: int):
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute("SELECT user_id FROM birthdays WHERE day=? AND month=?;", (day, month)).fetchall()
    return [r[0] for r in rows]

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

def now_cr():
    return dt.datetime.utcnow() + dt.timedelta(hours=TZ_OFFSET_HOURS)

@bot.event
async def on_ready():
    init_db()
    try:
        synced = await bot.tree.sync()
        print(f"✅ Bot listo. Slash commands sincronizados: {len(synced)}")
    except Exception as e:
        print("⚠️ No se pudo sync:", e)

    if not birthday_loop.is_running():
        birthday_loop.start()

@bot.tree.command(name="cumple_set", description="Guardar tu cumpleaños (día mes). Ej: 15 8")
@app_commands.describe(day="Día (1-31)", month="Mes (1-12)")
async def cumple_set_cmd(interaction: discord.Interaction, day: int, month: int):
    if not (1 <= month <= 12 and 1 <= day <= 31):
        await interaction.response.send_message("❌ Fecha inválida. Ej: `/cumple_set 15 8`", ephemeral=True)
        return
    set_birthday(interaction.user.id, day, month)
    await interaction.response.send_message(f"✅ Guardado: **{day:02d}/{month:02d}**", ephemeral=True)

@bot.tree.command(name="cumple_remove", description="Eliminar tu cumpleaños guardado")
async def cumple_remove_cmd(interaction: discord.Interaction):
    remove_birthday(interaction.user.id)
    await interaction.response.send_message("🗑️ Eliminado.", ephemeral=True)

@bot.tree.command(name="cumple_list", description="Ver lista de cumpleaños guardados")
async def cumple_list_cmd(interaction: discord.Interaction):
    rows = list_birthdays()
    if not rows:
        await interaction.response.send_message("No hay cumpleaños guardados todavía.", ephemeral=True)
        return
    lines = [f"<@{uid}> — {d:02d}/{m:02d}" for uid, d, m in rows]
    text = "\n".join(lines)
    if len(text) > 1800:
        text = text[:1800] + "\n... (lista muy larga)"
    await interaction.response.send_message(text, ephemeral=True)

_last_announcement_date = None

@tasks.loop(minutes=1)
async def birthday_loop():
    global _last_announcement_date

    t = now_cr()
    if t.hour != DEFAULT_ANNOUNCE_HOUR or t.minute != 0:
        return

    today = t.date()
    if _last_announcement_date == today:
        return

    _last_announcement_date = today
    user_ids = birthdays_for(today.day, today.month)
    if not user_ids:
        return

    channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if channel is None:
        return

    mentions = " ".join(f"<@{uid}>" for uid in user_ids)
    await channel.send(f"🎉 ¡Feliz cumpleaños! {mentions} 🥳🎂")

@birthday_loop.before_loop
async def before_birthday_loop():
    await bot.wait_until_ready()

import threading
from aiohttp import web

async def health(request):
    return web.Response(text="ok")

def run_web():
    app = web.Application()
    app.router.add_get("/", health)
    port = int(os.getenv("PORT", "10000"))
    web.run_app(app, host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()

bot.run(DISCORD_TOKEN)

