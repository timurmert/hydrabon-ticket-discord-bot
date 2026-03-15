import discord
from discord.ext import commands, tasks
import os
import datetime
from dotenv import load_dotenv
import pytz

from config import TURKEY_TIMEZONE, INACTIVITY_HOURS, CHECK_INTERVAL_HOURS
from database import create_database, get_db_connection
from views import TicketSelectView, TicketActionsView
from commands import setup_commands
from utils import auto_close_ticket

# .env dosyasını yükle
load_dotenv()

# Bot yapılandırması
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


@bot.event
async def on_ready():
    print(f"{bot.user} olarak giriş yapıldı!")
    create_database()

    try:
        synced = await bot.tree.sync()
        print(f"{len(synced)} komut senkronize edildi.")
    except Exception as e:
        print(f"Komutlar senkronize edilirken hata oluştu: {e}")

    # Kalıcı view'ları yeniden başlatma
    bot.add_view(TicketSelectView())
    bot.add_view(TicketActionsView())

    # Otomatik ticket kontrolünü başlat
    if not check_inactive_tickets.is_running():
        check_inactive_tickets.start()
        print("Otomatik ticket kontrolü başlatıldı.")

    await bot.change_presence(
        activity=discord.Streaming(
            name="HydRaboN", url="https://www.twitch.tv/mrpresidentnotsjanymore"
        )
    )


@tasks.loop(hours=CHECK_INTERVAL_HOURS)
async def check_inactive_tickets():
    """24 saat boyunca mesaj yazılmayan ticket'ları kontrol eder."""
    conn = get_db_connection()
    cursor = conn.cursor()

    twenty_four_hours_ago = datetime.datetime.now(TURKEY_TIMEZONE) - datetime.timedelta(
        hours=INACTIVITY_HOURS
    )

    cursor.execute("""
        SELECT ticket_id, user_id, channel_id, category
        FROM tickets
        WHERE status = 'open'
    """)

    active_tickets = cursor.fetchall()

    for ticket_id, user_id, channel_id, category_key in active_tickets:
        channel = bot.get_channel(channel_id)

        if not channel:
            cursor.execute(
                "UPDATE tickets SET status = 'closed', closed_at = ? WHERE ticket_id = ?",
                (datetime.datetime.now(TURKEY_TIMEZONE), ticket_id),
            )
            continue

        try:
            last_message = None
            async for message in channel.history(limit=1):
                last_message = message
                break

            if last_message:
                message_time = last_message.created_at.replace(tzinfo=pytz.UTC).astimezone(
                    TURKEY_TIMEZONE
                )
                if message_time < twenty_four_hours_ago:
                    await auto_close_ticket(ticket_id, user_id, channel_id, category_key)
            else:
                cursor.execute(
                    "SELECT created_at FROM tickets WHERE ticket_id = ?", (ticket_id,)
                )
                result = cursor.fetchone()
                if result:
                    created_at = result[0]
                    if isinstance(created_at, str):
                        created_at = datetime.datetime.fromisoformat(created_at)
                    if created_at.tzinfo is None:
                        created_at = TURKEY_TIMEZONE.localize(created_at)
                    else:
                        created_at = created_at.astimezone(TURKEY_TIMEZONE)

                    if created_at < twenty_four_hours_ago:
                        await auto_close_ticket(ticket_id, user_id, channel_id, category_key)

        except Exception as e:
            print(f"Ticket {ticket_id} kontrol edilirken hata: {e}")

    conn.commit()
    conn.close()


# Slash komutlarını kaydet
setup_commands(bot)

# Bot token
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    print(
        "HATA: DISCORD_TOKEN bulunamadı! Lütfen .env dosyasında tanımlayın veya çevresel değişken olarak ayarlayın."
    )
else:
    bot.run(TOKEN)
