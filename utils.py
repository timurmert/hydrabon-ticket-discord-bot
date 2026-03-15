import discord
import datetime
import asyncio
import io

from config import YETKILI_ROLLERI, TICKET_KATEGORILERI, TURKEY_TIMEZONE
from database import get_db_connection

# Bot referansı - circular import olmadan ticket1.py'den set edilir
_bot = None


def set_bot(bot_instance):
    """Bot referansını ayarlar. ticket1.py'den çağrılır."""
    global _bot
    _bot = bot_instance


def get_bot():
    """Bot referansını döndürür."""
    return _bot


def get_admin_role_ids():
    """YETKILI_ROLLERI dict'inden tüm rol ID'lerini döndürür."""
    return list(YETKILI_ROLLERI.values())


def is_admin(member: discord.Member) -> bool:
    """Üyenin yetkili rollerinden birine sahip olup olmadığını kontrol eder."""
    admin_role_ids = get_admin_role_ids()
    return any(role.id in admin_role_ids for role in member.roles)


async def log_action(guild_id, title, description, color, fields=None):
    """Log kanalına embed mesaj gönderir."""
    bot = get_bot()
    if not bot:
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT log_channel_id FROM config WHERE guild_id = ?", (guild_id,))
    result = cursor.fetchone()
    conn.close()

    if not result or not result[0]:
        return

    log_channel = bot.get_channel(result[0])
    if not log_channel:
        return

    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.datetime.now(TURKEY_TIMEZONE),
    )

    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)

    embed.set_footer(text="HydRaboN Ticket Sistemi")

    try:
        await log_channel.send(embed=embed)
    except Exception as e:
        print(f"Log gönderilemedi: {e}")


async def update_ticket_permissions(channel, guild, ticket_owner_id, admin_id):
    """Ticket kanalı izinlerini günceller: sadece ticket sahibi ve ilgili yetkili görebilir."""
    admin_role_ids = get_admin_role_ids()

    # Ticket sahibinin izinlerini koru
    ticket_owner = guild.get_member(ticket_owner_id)
    if ticket_owner:
        await channel.set_permissions(ticket_owner, read_messages=True, send_messages=True)

    # Yetkili rollerinin izinlerini kaldır
    for role_id in admin_role_ids:
        role = guild.get_role(role_id)
        if role:
            await channel.set_permissions(role, overwrite=None)

    # Yetkili kişinin izinlerini ekle
    admin = guild.get_member(admin_id)
    if admin:
        await channel.set_permissions(admin, read_messages=True, send_messages=True)


async def create_transcript(channel):
    """Kanal mesaj geçmişinden transcript oluşturur."""
    messages = []

    async for message in channel.history(limit=None, oldest_first=True):
        if message.author.bot and not message.embeds:
            continue

        content = message.content if message.content else ""

        # Ek dosyalar
        attachments = []
        for attachment in message.attachments:
            attachments.append(f"[Ek Dosya: {attachment.filename}]({attachment.url})")

        if attachments:
            content += "\n" + "\n".join(attachments)

        # Embed'ler
        if message.embeds:
            for embed in message.embeds:
                if embed.title:
                    content += f"\n**{embed.title}**"
                if embed.description:
                    content += f"\n{embed.description}"
                for field in embed.fields:
                    content += f"\n**{field.name}**: {field.value}"

        messages.append(
            {
                "author": str(message.author),
                "author_id": message.author.id,
                "content": content,
                "created_at": message.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "is_bot": message.author.bot,
            }
        )

    return messages


async def create_new_ticket(interaction: discord.Interaction, category_key: str):
    """Yeni ticket kanalı oluşturur."""
    from views import TicketActionsView

    user_id = interaction.user.id
    guild = interaction.guild
    kategori = TICKET_KATEGORILERI[category_key]

    conn = get_db_connection()
    cursor = conn.cursor()

    # Kullanıcının açık bir ticket'ı var mı kontrol et
    cursor.execute(
        "SELECT channel_id FROM tickets WHERE user_id = ? AND status = 'open'", (user_id,)
    )
    existing_ticket = cursor.fetchone()

    if existing_ticket:
        channel = guild.get_channel(existing_ticket[0])
        if channel:
            conn.close()
            return None

    # Yapılandırma bilgilerini al
    cursor.execute(
        "SELECT ticket_count, ticket_channel_id FROM config WHERE guild_id = ?", (guild.id,)
    )
    config = cursor.fetchone()

    if not config:
        conn.close()
        return None

    ticket_count = config[0] + 1

    # Yeni ticket sayısını güncelle
    cursor.execute("UPDATE config SET ticket_count = ? WHERE guild_id = ?", (ticket_count, guild.id))

    # Ticket ID ve kanal adı
    kisaltma = kategori["kisaltma"].lower()
    ticket_id = f"{kisaltma}-{ticket_count:04d}"
    channel_name = f"{kisaltma}-{interaction.user.name}"

    # İzinler
    admin_role_ids = get_admin_role_ids()
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
    }

    for role_id in admin_role_ids:
        role = guild.get_role(role_id)
        if role:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

    # Setup kanalının kategorisini kullan
    ticket_channel_id = config[1]
    ticket_channel = guild.get_channel(ticket_channel_id)
    category_channel = ticket_channel.category if ticket_channel and ticket_channel.category else None

    if not category_channel:
        category_channel = discord.utils.get(guild.categories, name="Tickets")
        if not category_channel:
            category_channel = await guild.create_category("Tickets")

    channel = await guild.create_text_channel(
        name=channel_name,
        category=category_channel,
        overwrites=overwrites,
        topic=f"Kategori: {kategori['label']} | Ticket Sahibi: {interaction.user.mention} | ID: {ticket_id}",
    )

    # Ticket'ı veritabanına kaydet
    cursor.execute(
        "INSERT INTO tickets (ticket_id, user_id, channel_id, status, category, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (ticket_id, user_id, channel.id, "open", category_key, datetime.datetime.now(TURKEY_TIMEZONE)),
    )

    conn.commit()
    conn.close()

    # Ticket açılış embed'i
    embed = discord.Embed(
        title=f"{kategori['emoji']} Ticket: {ticket_id.upper()}",
        description=(
            f"**Kategori:** {kategori['label']}\n\n"
            f"Merhaba {interaction.user.mention}, destek talebiniz oluşturuldu.\n\n"
            f"\u23f0 **Bu ticket, son mesajdan 24 saat sonra mesaj atılmamışsa otomatik olarak silinecektir.**\n"
            f"\U0001f465 **Yetkililerden müsait olan birisi en kısa sürede talebinize bakacaktır.**\n\n"
            f"Lütfen sorununuzu bu kanalda detaylı bir şekilde açıklayın."
        ),
        color=discord.Color.green(),
        timestamp=datetime.datetime.now(TURKEY_TIMEZONE),
    )
    embed.set_footer(text=f"HydRaboN Ticket Sistemi \u2022 {guild.name}")

    await channel.send(embed=embed, view=TicketActionsView())

    return channel


async def close_ticket(interaction: discord.Interaction, transcript=None):
    """Ticket'ı kapatır, transcript'i log kanalına gönderir ve kanalı siler."""
    channel = interaction.channel

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT ticket_id, user_id, category FROM tickets WHERE channel_id = ? AND status = 'open'",
        (channel.id,),
    )
    ticket = cursor.fetchone()

    if not ticket:
        await interaction.followup.send(
            "Bu kanal bir ticket değil veya zaten kapatılmış.", ephemeral=True
        )
        conn.close()
        return False

    ticket_id, ticket_owner_id, category_key = ticket

    # Yalnızca ticket sahibi veya yetkili kullanıcılar kapatabilir
    has_permission = interaction.user.id == ticket_owner_id or is_admin(interaction.user)

    if not has_permission:
        await interaction.followup.send("Bu ticket'ı kapatma yetkiniz yok.", ephemeral=True)
        conn.close()
        return False

    # Log kanalını al
    cursor.execute("SELECT log_channel_id FROM config WHERE guild_id = ?", (interaction.guild.id,))
    config = cursor.fetchone()
    log_channel_id = config[0] if config else None

    # Ticket'ı kapat
    cursor.execute(
        "UPDATE tickets SET status = 'closed', closed_at = ? WHERE channel_id = ?",
        (datetime.datetime.now(TURKEY_TIMEZONE), channel.id),
    )

    conn.commit()
    conn.close()

    # Kapanış mesajı
    close_embed = discord.Embed(
        title="Ticket Kapatılıyor",
        description=f"Bu ticket {interaction.user.mention} tarafından kapatıldı.\nKanal 5 saniye içinde silinecek.",
        color=discord.Color.red(),
        timestamp=datetime.datetime.now(TURKEY_TIMEZONE),
    )

    await interaction.followup.send(embed=close_embed)

    # Transcript log kanalına gönder
    if transcript and log_channel_id:
        log_channel = interaction.guild.get_channel(log_channel_id)
        if log_channel:
            kategori_label = TICKET_KATEGORILERI.get(category_key, {}).get("label", category_key)

            # Önce bilgi embed'i gönder
            info_embed = discord.Embed(
                title=f"\U0001f4cb Ticket Kapatıldı: {ticket_id}",
                color=discord.Color.red(),
                timestamp=datetime.datetime.now(TURKEY_TIMEZONE),
            )
            info_embed.add_field(name="Ticket ID", value=ticket_id, inline=True)
            info_embed.add_field(name="Kategori", value=kategori_label, inline=True)
            info_embed.add_field(
                name="Ticket Sahibi", value=f"<@{ticket_owner_id}>", inline=True
            )
            info_embed.add_field(
                name="Kapatan Kullanıcı",
                value=f"{interaction.user.mention} ({interaction.user.id})",
                inline=True,
            )
            info_embed.add_field(name="Kanal", value=f"#{channel.name}", inline=True)
            info_embed.add_field(
                name="Kapatılma Tarihi",
                value=datetime.datetime.now(TURKEY_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S"),
                inline=True,
            )
            info_embed.set_footer(text="HydRaboN Ticket Sistemi")

            # Transcript dosyası oluştur
            transcript_content = f"# Ticket Transcript: {ticket_id}\n"
            transcript_content += f"# Kategori: {kategori_label}\n"
            transcript_content += f"# Ticket Sahibi: <@{ticket_owner_id}>\n"
            transcript_content += f"# Kapatıldığı Tarih: {datetime.datetime.now(TURKEY_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}\n\n"

            for msg in transcript:
                bot_tag = " [BOT]" if msg["is_bot"] else ""
                transcript_content += f"{msg['author']}{bot_tag} - {msg['created_at']}\n"
                transcript_content += f"{msg['content']}\n\n"

            transcript_file = discord.File(
                fp=io.BytesIO(transcript_content.encode("utf-8")),
                filename=f"transcript-{ticket_id}.md",
            )

            try:
                await log_channel.send(embed=info_embed, file=transcript_file)
            except Exception as e:
                print(f"Transcript gönderilemedi: {e}")

    await asyncio.sleep(5)
    await channel.delete()

    return True


async def auto_close_ticket(ticket_id, user_id, channel_id, category_key):
    """24 saat inaktif olan ticket'ı otomatik kapatır."""
    bot = get_bot()
    if not bot:
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE tickets SET status = 'closed', closed_at = ? WHERE ticket_id = ?",
        (datetime.datetime.now(TURKEY_TIMEZONE), ticket_id),
    )

    # Kullanıcıya DM gönder
    kategori_label = TICKET_KATEGORILERI.get(category_key, {}).get("label", category_key)
    try:
        user = await bot.fetch_user(user_id)
        if user:
            embed = discord.Embed(
                title="Ticket Otomatik Kapatıldı",
                description=(
                    f"Merhaba {user.name},\n\n"
                    f"Ticket'ınız ({ticket_id}) 24 saat boyunca aktif olmadığı için otomatik olarak kapatılmıştır.\n\n"
                    f"**Kategori:** {kategori_label}\n\n"
                    f"Eğer hala yardıma ihtiyacınız varsa, yeni bir ticket oluşturabilirsiniz."
                ),
                color=discord.Color.orange(),
                timestamp=datetime.datetime.now(TURKEY_TIMEZONE),
            )
            embed.set_footer(text="HydRaboN Ticket Sistemi")
            await user.send(embed=embed)
    except Exception as e:
        print(f"Kullanıcıya DM gönderilemedi: {e}")

    # Kanalı sil
    channel = bot.get_channel(channel_id)
    if channel:
        try:
            embed = discord.Embed(
                title="Ticket Otomatik Kapatılıyor",
                description="Bu ticket 24 saat boyunca aktif olmadığı için otomatik olarak kapatıldı.\nKanal 5 saniye içinde silinecek.",
                color=discord.Color.orange(),
                timestamp=datetime.datetime.now(TURKEY_TIMEZONE),
            )
            await channel.send(embed=embed)
            await asyncio.sleep(5)
            await channel.delete()
        except Exception as e:
            print(f"Kanal silinirken hata: {e}")

    # Log kaydı
    guild_id = None
    if channel:
        guild_id = channel.guild.id
    else:
        cursor.execute("SELECT guild_id FROM config LIMIT 1")
        result = cursor.fetchone()
        if result:
            guild_id = result[0]

    if guild_id:
        await log_action(
            guild_id,
            "Ticket Otomatik Kapatıldı",
            f"Ticket ({ticket_id}) 24 saat boyunca aktif olmadığı için otomatik olarak kapatıldı.",
            discord.Color.orange(),
            [
                ("Ticket ID", ticket_id, True),
                ("Kullanıcı", f"<@{user_id}>", True),
                ("Kategori", kategori_label, False),
                ("Sebep", "24 saat boyunca aktif değildi", False),
            ],
        )

    conn.commit()
    conn.close()
