import discord
from discord.ext import commands, tasks
from discord import app_commands, ui
import sqlite3
import os
import datetime
import asyncio
from typing import Optional, List
from dotenv import load_dotenv
import io
import pytz

# Türkiye zaman dilimi
TURKEY_TIMEZONE = pytz.timezone('Europe/Istanbul')

# .env dosyasını yükle
load_dotenv()

# SQLite datetime dönüştürücüleri
def adapt_datetime(dt):
    return dt.isoformat()

def convert_datetime(s):
    try:
        return datetime.datetime.fromisoformat(s.decode())
    except:
        return datetime.datetime.fromisoformat(s)

# SQLite'a datetime dönüştürücüleri kaydet
sqlite3.register_adapter(datetime.datetime, adapt_datetime)
sqlite3.register_converter("timestamp", convert_datetime)

# Bot yapılandırması
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# Veritabanı bağlantısı
def create_database():
    conn = sqlite3.connect('ticket_database.db', detect_types=sqlite3.PARSE_DECLTYPES)
    cursor = conn.cursor()
    
    # Ticket tablosu
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tickets (
        ticket_id TEXT PRIMARY KEY,
        user_id INTEGER,
        channel_id INTEGER,
        status TEXT,
        subject TEXT,
        description TEXT,
        created_at timestamp,
        closed_at timestamp
    )
    ''')
    
    # Admin yardım tablosu
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS ticket_helpers (
        ticket_id TEXT,
        admin_id INTEGER,
        joined_at timestamp,
        FOREIGN KEY (ticket_id) REFERENCES tickets (ticket_id)
    )
    ''')
    
    # Yapılandırma tablosu
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS config (
        guild_id INTEGER,
        ticket_channel_id INTEGER,
        admin_role_ids TEXT,
        log_channel_id INTEGER,
        ticket_count INTEGER DEFAULT 0
    )
    ''')
    
    conn.commit()
    conn.close()

# Veritabanı bağlantısı açma yardımcı fonksiyonu
def get_db_connection():
    return sqlite3.connect('ticket_database.db', detect_types=sqlite3.PARSE_DECLTYPES)

# Ticket oluşturma butonu için UI sınıfı
class TicketView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label='Destek Talebi Oluştur', style=discord.ButtonStyle.success, emoji='🎫', custom_id='create_ticket')
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketModal())

# Ticket oluşturma için modal sınıfı
class TicketModal(ui.Modal, title="Yeni Destek Talebi"):
    ticket_subject = ui.TextInput(
        label="Konu",
        placeholder="Lütfen destek talebinizin konusunu belirtin",
        required=True,
        max_length=100
    )
    
    ticket_description = ui.TextInput(
        label="Açıklama",
        placeholder="Lütfen sorununuzu detaylı bir şekilde açıklayın",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        # Hemen yanıt vermek için defer kullanıyoruz
        await interaction.response.defer(ephemeral=True)
        
        # Ticket oluştur
        channel = await create_new_ticket(interaction, self.ticket_subject.value, self.ticket_description.value)
        
        # İşlem tamamlandıktan sonra kullanıcıya bilgi ver
        if channel:
            await interaction.followup.send(f"Ticket'ınız oluşturuldu: {channel.mention}", ephemeral=True)
        else:
            await interaction.followup.send("Ticket oluşturulurken bir hata oluştu veya zaten açık bir ticket'ınız var.", ephemeral=True)

# Ticket butonları için UI sınıfı
class TicketActionsView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label='Ticket\'ı Kapat', style=discord.ButtonStyle.danger, emoji='🔒', custom_id='close_ticket')
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Interaction'ı hemen yanıtla
        await interaction.response.defer(ephemeral=True)
        
        # Ticket mesajlarının bir kopyasını oluştur (log için)
        transcript = await create_transcript(interaction.channel)
        
        # Ticket'ı kapat
        success = await close_ticket(interaction, transcript)
        
        if not success:
            await interaction.followup.send("Ticket kapatılırken bir hata oluştu.", ephemeral=True)

    @discord.ui.button(label='Yardım Et', style=discord.ButtonStyle.primary, emoji='👋', custom_id='join_ticket')
    async def join_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # İşlemi başlat
        await interaction.response.defer(ephemeral=True)
        
        channel = interaction.channel
        
        # Veritabanı bağlantısı kur
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Bu kanalın bir ticket olup olmadığını kontrol et
        cursor.execute("SELECT ticket_id, user_id FROM tickets WHERE channel_id = ? AND status = 'open'", (channel.id,))
        ticket = cursor.fetchone()
        
        if not ticket:
            await interaction.followup.send("Bu kanal bir ticket değil veya kapatılmış.", ephemeral=True)
            conn.close()
            return
        
        ticket_id, ticket_owner_id = ticket
        
        # Kullanıcının yetkili olup olmadığını kontrol et
        cursor.execute("SELECT admin_role_ids FROM config WHERE guild_id = ?", (interaction.guild.id,))
        config = cursor.fetchone()
        
        if not config:
            await interaction.followup.send("Ticket yapılandırması bulunamadı.", ephemeral=True)
            conn.close()
            return
        
        admin_role_ids = config[0].split(',') if ',' in config[0] else [config[0]]
        is_admin = False
        
        for role_id in admin_role_ids:
            try:
                if interaction.guild.get_role(int(role_id)) in interaction.user.roles:
                    is_admin = True
                    break
            except (ValueError, AttributeError):
                continue
        
        if not is_admin:
            await interaction.followup.send("Bu butonu kullanmak için yetkiniz yok.", ephemeral=True)
            conn.close()
            return
        
        # Kullanıcı zaten yardımcı olarak eklenmiş mi kontrol et
        cursor.execute("SELECT * FROM ticket_helpers WHERE ticket_id = ? AND admin_id = ?", 
                      (ticket_id, interaction.user.id))
        helper = cursor.fetchone()
        
        if helper:
            await interaction.followup.send("Bu ticket'a zaten yardımcı olarak eklendiniz.", ephemeral=True)
            conn.close()
            return
        
        # Yardımcı olarak ekle
        cursor.execute(
            "INSERT INTO ticket_helpers (ticket_id, admin_id, joined_at) VALUES (?, ?, ?)",
            (ticket_id, interaction.user.id, datetime.datetime.now(TURKEY_TIMEZONE))
        )
        
        conn.commit()
        conn.close()
        
        # İzinleri düzenle - Diğer tüm yetkililerden izinleri kaldır ve sadece bu yetkiliye ve ticket sahibine ver
        await update_ticket_permissions(channel, interaction.guild, int(ticket_owner_id), interaction.user.id, admin_role_ids)
        
        embed = discord.Embed(
            title="Yeni Yetkili",
            description=f"{interaction.user.mention} bu ticket'a yardımcı olarak katıldı.",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(TURKEY_TIMEZONE)
        )
        
        await interaction.followup.send(embed=embed)
        
        # Log kaydı
        await log_action(
            interaction.guild.id,
            "Yetkili Katıldı",
            f"Bir yetkili ticket'a ({ticket_id}) katıldı.",
            discord.Color.green(),
            [
                ("Yetkili", f"{interaction.user.mention} ({interaction.user.id})", True)
            ]
        )
    
    @discord.ui.button(label='Yetkili Ekle', style=discord.ButtonStyle.success, emoji='👥', custom_id='add_admin')
    async def add_admin(self, interaction: discord.Interaction, button: discord.ui.Button):
        # İşlemi başlat
        await interaction.response.defer(ephemeral=True)
        
        channel = interaction.channel
        
        # Veritabanı bağlantısı kur
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Bu kanalın bir ticket olup olmadığını kontrol et
        cursor.execute("SELECT ticket_id, user_id FROM tickets WHERE channel_id = ? AND status = 'open'", (channel.id,))
        ticket = cursor.fetchone()
        
        if not ticket:
            await interaction.followup.send("Bu kanal bir ticket değil veya kapatılmış.", ephemeral=True)
            conn.close()
            return
        
        ticket_id, ticket_owner_id = ticket
        
        # Kullanıcının halihazırda yardımcı olup olmadığını kontrol et
        cursor.execute("SELECT * FROM ticket_helpers WHERE ticket_id = ? AND admin_id = ?", 
                      (ticket_id, interaction.user.id))
        helper = cursor.fetchone()
        
        if not helper:
            await interaction.followup.send("Bu ticket'ta yetkili değilsiniz. Önce 'Yardım Et' butonunu kullanmalısınız.", ephemeral=True)
            conn.close()
            return
        
        # Admin rol listesini al
        cursor.execute("SELECT admin_role_ids FROM config WHERE guild_id = ?", (interaction.guild.id,))
        config = cursor.fetchone()
        admin_role_ids = config[0].split(',') if ',' in config[0] else [config[0]]
        
        # Halihazırda bu ticket'a yardım eden yetkililer
        cursor.execute("SELECT admin_id FROM ticket_helpers WHERE ticket_id = ?", (ticket_id,))
        existing_helpers = [row[0] for row in cursor.fetchall()]
        
        # Yetkili listesini oluştur
        guild = interaction.guild
        admin_options = []
        
        # Her rol için o role sahip üyeleri bul
        for role_id in admin_role_ids:
            try:
                role = guild.get_role(int(role_id))
                if role:
                    for member in role.members:
                        # Kendisi veya mevcut yardımcılar değilse ekle
                        if member.id != interaction.user.id and member.id not in existing_helpers:
                            # Aynı üye birden fazla rol ile eklenmemeli
                            if not any(option.value == str(member.id) for option in admin_options):
                                admin_options.append(
                                    discord.SelectOption(
                                        label=member.display_name,
                                        value=str(member.id),
                                        description=f"ID: {member.id}"
                                    )
                                )
            except (ValueError, AttributeError):
                continue
        
        conn.close()
        
        # Eğer eklenebilecek yetkili yoksa bildir
        if not admin_options:
            await interaction.followup.send("Eklenebilecek başka yetkili bulunamadı.", ephemeral=True)
            return
        
        # Modal oluştur
        modal = AdminSelectModal(admin_options, ticket_id, int(ticket_owner_id))
        await interaction.followup.send("Lütfen eklemek istediğiniz yetkiliyi seçin:", view=modal, ephemeral=True)

# Yetkili ekleme modalı
class AdminSelectModal(discord.ui.View):
    def __init__(self, admin_options, ticket_id, ticket_owner_id):
        super().__init__(timeout=180)  # 3 dakikalık timeout
        
        # Dropdown ekle
        self.add_item(AdminSelectDropdown(admin_options, ticket_id, ticket_owner_id))

# Yetkili seçme dropdown'u
class AdminSelectDropdown(discord.ui.Select):
    def __init__(self, admin_options, ticket_id, ticket_owner_id):
        self.ticket_id = ticket_id
        self.ticket_owner_id = ticket_owner_id
        
        super().__init__(
            placeholder="Eklemek istediğiniz yetkiliyi seçin...",
            min_values=1,
            max_values=1,
            options=admin_options
        )
    
    async def callback(self, interaction: discord.Interaction):
        # İşlemi başlat
        await interaction.response.defer(ephemeral=True)
        
        selected_admin_id = int(self.values[0])
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Ticket kanalını bul
        cursor.execute("SELECT channel_id FROM tickets WHERE ticket_id = ?", (self.ticket_id,))
        result = cursor.fetchone()
        
        if not result:
            await interaction.followup.send("Ticket bilgileri bulunamadı.", ephemeral=True)
            conn.close()
            return
        
        channel_id = result[0]
        
        # Yetkili zaten eklenmiş mi kontrol et
        cursor.execute("SELECT * FROM ticket_helpers WHERE ticket_id = ? AND admin_id = ?", 
                       (self.ticket_id, selected_admin_id))
        helper = cursor.fetchone()
        
        if helper:
            await interaction.followup.send("Bu yetkili zaten ticket'a eklenmiş.", ephemeral=True)
            conn.close()
            return
        
        # Yetkiliyi ekle
        cursor.execute(
            "INSERT INTO ticket_helpers (ticket_id, admin_id, joined_at) VALUES (?, ?, ?)",
            (self.ticket_id, selected_admin_id, datetime.datetime.now(TURKEY_TIMEZONE))
        )
        
        conn.commit()
        conn.close()
        
        # Kanalı bul
        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            await interaction.followup.send("Ticket kanalı bulunamadı.", ephemeral=True)
            return
        
        # Yetkiliyi bul
        selected_member = interaction.guild.get_member(selected_admin_id)
        if not selected_member:
            await interaction.followup.send("Seçilen yetkili bulunamadı.", ephemeral=True)
            return
        
        # İzinleri ayarla
        await channel.set_permissions(selected_member, read_messages=True, send_messages=True)
        
        # Bildirim gönder
        embed = discord.Embed(
            title="Yetkili Eklendi",
            description=f"{selected_member.mention} ticket'a {interaction.user.mention} tarafından eklendi.",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(TURKEY_TIMEZONE)
        )
        
        await channel.send(embed=embed)
        
        # Log kaydı
        await log_action(
            interaction.guild.id,
            "Yetkili Eklendi",
            f"Bir yetkili ticket'a ({self.ticket_id}) eklendi.",
            discord.Color.green(),
            [
                ("Eklenen Yetkili", f"{selected_member.mention} ({selected_admin_id})", True),
                ("Ekleyen Yetkili", f"{interaction.user.mention} ({interaction.user.id})", True)
            ]
        )
        
        await interaction.followup.send(f"{selected_member.mention} ticket'a başarıyla eklendi.", ephemeral=True)

# Ticket izinlerini güncelleme fonksiyonu
async def update_ticket_permissions(channel, guild, ticket_owner_id, admin_id, admin_role_ids):
    # Ticket sahibinin izinlerini koru
    ticket_owner = guild.get_member(ticket_owner_id)
    if ticket_owner:
        await channel.set_permissions(ticket_owner, read_messages=True, send_messages=True)
    
    # Yetkili rollerinin izinlerini kaldır (öncelikle herkesten izinleri kaldır)
    for role_id in admin_role_ids:
        try:
            role = guild.get_role(int(role_id))
            if role:
                await channel.set_permissions(role, overwrite=None)  # Rol izinlerini kaldır
        except (ValueError, AttributeError):
            continue
    
    # Yetkili kişinin izinlerini ekle
    admin = guild.get_member(admin_id)
    if admin:
        await channel.set_permissions(admin, read_messages=True, send_messages=True)

# Transcript oluşturma fonksiyonu - log için kalıyor
async def create_transcript(channel):
    messages = []
    
    # Kanalın tüm mesajlarını topla
    async for message in channel.history(limit=None, oldest_first=True):
        if message.author.bot and not message.embeds:
            continue  # Bot mesajlarını atla (gömülü olmayan)
        
        # Mesaj içeriği
        content = message.content if message.content else ""
        
        # Ek mesaj içeriği (görseller, dosyalar)
        attachments = []
        for attachment in message.attachments:
            attachments.append(f"[Ek Dosya: {attachment.filename}]({attachment.url})")
        
        # Görseller varsa ekle
        if attachments:
            content += "\n" + "\n".join(attachments)
        
        # Embed varsa ekle
        if message.embeds:
            for embed in message.embeds:
                if embed.title:
                    content += f"\n**{embed.title}**"
                if embed.description:
                    content += f"\n{embed.description}"
                for field in embed.fields:
                    content += f"\n**{field.name}**: {field.value}"
        
        # Mesaj detaylarını listeye ekle
        messages.append({
            "author": str(message.author),
            "author_id": message.author.id,
            "content": content,
            "created_at": message.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "is_bot": message.author.bot
        })
    
    return messages

# Ticket kapatma fonksiyonu
async def close_ticket(interaction: discord.Interaction, transcript=None):
    channel = interaction.channel
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Bu kanalın bir ticket olup olmadığını kontrol et
    cursor.execute("SELECT ticket_id, user_id, subject FROM tickets WHERE channel_id = ? AND status = 'open'", (channel.id,))
    ticket = cursor.fetchone()
    
    if not ticket:
        await interaction.followup.send("Bu kanal bir ticket değil veya zaten kapatılmış.", ephemeral=True)
        conn.close()
        return False
    
    ticket_id, ticket_owner_id, subject = ticket
    
    # Yalnızca ticket sahibi veya yetkili kullanıcılar kapatabilir
    cursor.execute("SELECT admin_role_ids, log_channel_id FROM config WHERE guild_id = ?", (interaction.guild.id,))
    config = cursor.fetchone()
    
    if not config:
        await interaction.followup.send("Ticket yapılandırması bulunamadı.", ephemeral=True)
        conn.close()
        return False
    
    admin_role_ids = config[0].split(',') if ',' in config[0] else [config[0]]
    log_channel_id = config[1]
    
    has_permission = False
    
    # Kullanıcı ticket sahibi mi?
    if interaction.user.id == ticket_owner_id:
        has_permission = True
    else:
        # Kullanıcı yetkili rolüne sahip mi?
        for role_id in admin_role_ids:
            try:
                if interaction.guild.get_role(int(role_id)) in interaction.user.roles:
                    has_permission = True
                    break
            except (ValueError, AttributeError):
                continue
    
    if not has_permission:
        await interaction.followup.send("Bu ticket'ı kapatma yetkiniz yok.", ephemeral=True)
        conn.close()
        return False
    
    # Ticket'ı kapat
    cursor.execute(
        "UPDATE tickets SET status = 'closed', closed_at = ? WHERE channel_id = ?",
        (datetime.datetime.now(TURKEY_TIMEZONE), channel.id)
    )
    
    conn.commit()
    conn.close()
    
    # Kapanış mesajı gönder
    embed = discord.Embed(
        title="Ticket Kapatılıyor",
        description=f"Bu ticket {interaction.user.mention} tarafından kapatıldı.\nKanal 5 saniye içinde silinecek.",
        color=discord.Color.red(),
        timestamp=datetime.datetime.now(TURKEY_TIMEZONE)
    )
    
    await interaction.followup.send(embed=embed)
    
    # Log kaydı
    if transcript and log_channel_id:
        log_channel = interaction.guild.get_channel(log_channel_id)
        if log_channel:
            # Transcript mesajlarını formatlı bir şekilde oluştur
            transcript_content  = f"# Ticket Transcript: {ticket_id}\n"
            transcript_content += f"# Konu: {subject}\n"
            transcript_content += f"# Ticket Sahibi: <@{ticket_owner_id}>\n"
            transcript_content += f"# Kapatıldığı Tarih: {datetime.datetime.now(TURKEY_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            
            for msg in transcript:
                bot_tag = " [BOT]" if msg["is_bot"] else ""
                transcript_content += f"{msg['author']}{bot_tag} - {msg['created_at']}\n"
                transcript_content += f"{msg['content']}\n\n"
            
            # Transcript dosyası oluştur
            transcript_file = discord.File(
                fp=io.BytesIO(transcript_content.encode('utf-8')),
                filename=f"transcript-{ticket_id}.md"
            )
            
            try:
                await log_channel.send(
                    content=f"Ticket {ticket_id} kapatıldı. İşte transcript:",
                    file=transcript_file
                )
            except Exception as e:
                print(f"Transcript gönderilemedi: {e}")
    
    await log_action(
        interaction.guild.id,
        "Ticket Kapatıldı",
        f"Ticket ({ticket_id}) kapatıldı.",
        discord.Color.red(),
        [
            ("Kapatılan Kanal", f"#{channel.name}", True),
            ("Kapatan Kullanıcı", f"{interaction.user.mention} ({interaction.user.id})", True),
            ("Ticket Sahibi", f"<@{ticket_owner_id}>", True)
        ]
    )
    
    # 5 saniye bekleyip kanalı sil
    await asyncio.sleep(5)
    await channel.delete()
    
    return True

# 24 saat boyunca mesaj yazılmayan ticket'ları kontrol et
@tasks.loop(hours=1)  # Her saat kontrol et
async def check_inactive_tickets():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 24 saat öncesini hesapla
    twenty_four_hours_ago = datetime.datetime.now(TURKEY_TIMEZONE) - datetime.timedelta(hours=24)
    
    # Tüm açık ticket'ları al
    cursor.execute("""
        SELECT ticket_id, user_id, channel_id, subject 
        FROM tickets 
        WHERE status = 'open'
    """)
    
    active_tickets = cursor.fetchall()
    
    for ticket_id, user_id, channel_id, subject in active_tickets:
        channel = bot.get_channel(channel_id)
        
        if not channel:
            # Kanal bulunamadıysa ticket'ı kapatılmış olarak işaretle
            cursor.execute(
                "UPDATE tickets SET status = 'closed', closed_at = ? WHERE ticket_id = ?",
                (datetime.datetime.now(TURKEY_TIMEZONE), ticket_id)
            )
            continue
        
        # Kanalın son mesajını kontrol et
        try:
            last_message = None
            async for message in channel.history(limit=1):
                last_message = message
                break
            
            if last_message:
                # Son mesajın 24 saatten eski olup olmadığını kontrol et
                message_time = last_message.created_at.replace(tzinfo=pytz.UTC).astimezone(TURKEY_TIMEZONE)
                if message_time < twenty_four_hours_ago:
                    # Ticket'ı otomatik kapat
                    await auto_close_ticket(ticket_id, user_id, channel_id, subject)
            else:
                # Hiç mesaj yoksa ticket'ın açılış tarihini kontrol et
                cursor.execute("SELECT created_at FROM tickets WHERE ticket_id = ?", (ticket_id,))
                result = cursor.fetchone()
                if result:
                    created_at = result[0]
                    # created_at'ı datetime objesine çevir ve timezone ekle
                    if isinstance(created_at, str):
                        created_at = datetime.datetime.fromisoformat(created_at)
                    if created_at.tzinfo is None:
                        created_at = TURKEY_TIMEZONE.localize(created_at)
                    else:
                        created_at = created_at.astimezone(TURKEY_TIMEZONE)
                    
                    if created_at < twenty_four_hours_ago:
                        await auto_close_ticket(ticket_id, user_id, channel_id, subject)
                
        except Exception as e:
            print(f"Ticket {ticket_id} kontrol edilirken hata: {e}")
    
    conn.commit()
    conn.close()

# Otomatik ticket kapatma fonksiyonu
async def auto_close_ticket(ticket_id, user_id, channel_id, subject):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Ticket'ı kapat
    cursor.execute(
        "UPDATE tickets SET status = 'closed', closed_at = ? WHERE ticket_id = ?",
        (datetime.datetime.now(TURKEY_TIMEZONE), ticket_id)
    )
    
    # Kullanıcıya DM gönder
    try:
        user = await bot.fetch_user(user_id)
        if user:
            embed = discord.Embed(
                title="Ticket Otomatik Kapatıldı",
                description=f"Merhaba {user.name},\n\nTicket'ınız ({ticket_id}) 24 saat boyunca aktif olmadığı için otomatik olarak kapatılmıştır.\n\n**Konu:** {subject}\n\nEğer hala yardıma ihtiyacınız varsa, yeni bir ticket oluşturabilirsiniz.",
                color=discord.Color.orange(),
                timestamp=datetime.datetime.now(TURKEY_TIMEZONE)
            )
            embed.set_footer(text="HydRaboN Ticket Sistemi")
            await user.send(embed=embed)
    except Exception as e:
        print(f"Kullanıcıya DM gönderilemedi: {e}")
    
    # Kanalı sil
    channel = bot.get_channel(channel_id)
    if channel:
        try:
            # Kapanış mesajı gönder
            embed = discord.Embed(
                title="Ticket Otomatik Kapatılıyor",
                description="Bu ticket 24 saat boyunca aktif olmadığı için otomatik olarak kapatıldı.\nKanal 5 saniye içinde silinecek.",
                color=discord.Color.orange(),
                timestamp=datetime.datetime.now(TURKEY_TIMEZONE)
            )
            await channel.send(embed=embed)
            
            # 5 saniye bekleyip kanalı sil
            await asyncio.sleep(5)
            await channel.delete()
        except Exception as e:
            print(f"Kanal silinirken hata: {e}")
    
    # Log kaydı
    guild_id = None
    if channel:
        guild_id = channel.guild.id
    elif user:
        # Kullanıcının hangi guild'den ticket açtığını bul
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
                ("Konu", subject, False),
                ("Sebep", "24 saat boyunca aktif değildi", False)
            ]
        )
    
    conn.commit()
    conn.close()

# Bot hazır olduğunda çalışacak fonksiyon
@bot.event
async def on_ready():
    print(f'{bot.user} olarak giriş yapıldı!')
    create_database()
    try:
        synced = await bot.tree.sync()
        print(f"{len(synced)} komut senkronize edildi.")
    except Exception as e:
        print(f"Komutlar senkronize edilirken hata oluştu: {e}")
    
    # Kalıcı butonları yeniden başlatma
    bot.add_view(TicketView())
    bot.add_view(TicketActionsView())
    
    # Otomatik ticket kontrolünü başlat
    if not check_inactive_tickets.is_running():
        check_inactive_tickets.start()
        print("Otomatik ticket kontrolü başlatıldı.")
    
    await bot.change_presence(activity=discord.Streaming(name="HydRaboN", url="https://www.twitch.tv/mrpresidentnotsjanymore"))

# Ticket sistemi kurulum komutu
@bot.tree.command(name="setup", description="Ticket sistemini kurar")
@app_commands.default_permissions(administrator=True)
async def setup(interaction: discord.Interaction, kanal: discord.TextChannel, yetkili_rol: discord.Role, log_kanal: discord.TextChannel = None):
    await interaction.response.defer(ephemeral=True)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Mevcut yapılandırmayı kontrol et
    cursor.execute("SELECT * FROM config WHERE guild_id = ?", (interaction.guild.id,))
    existing_config = cursor.fetchone()
    
    if existing_config:
        cursor.execute("UPDATE config SET ticket_channel_id = ?, admin_role_ids = ?, log_channel_id = ? WHERE guild_id = ?", 
                      (kanal.id, str(yetkili_rol.id), log_kanal.id if log_kanal else None, interaction.guild.id))
    else:
        cursor.execute("INSERT INTO config (guild_id, ticket_channel_id, admin_role_ids, log_channel_id, ticket_count) VALUES (?, ?, ?, ?, ?)", 
                      (interaction.guild.id, kanal.id, str(yetkili_rol.id), log_kanal.id if log_kanal else None, 0))
    
    conn.commit()
    conn.close()
    
    embed = discord.Embed(
        title="📋 HydRaboN Ticket Sistemi",
        description="Teknik sorun veya önerileriniz için ticket talebi oluşturabilirsiniz.\n\n**✅ Hızlı Yanıt**\n**👥 Özel Destek**\n**🔒 Güvenli İletişim**\n\nAşağıdaki butona tıklayarak ticket talebi oluşturabilirsiniz.",
        color=discord.Color.brand_green()
    )
    embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1109802773839134772/1118864108351655936/HydRaboN.png")
    embed.set_footer(text=f"HydRaboN Ticket Sistemi • {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
    
    await kanal.send(embed=embed, view=TicketView())
    
    log_mesaj = "Ticket sistemi başarıyla kuruldu."
    if log_kanal:
        log_mesaj += f" Log kanalı: {log_kanal.mention}"
        
    await interaction.followup.send(log_mesaj, ephemeral=True)

# Log kaydı fonksiyonu
async def log_action(guild_id, title, description, color, fields=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Log kanalını kontrol et
    cursor.execute("SELECT log_channel_id FROM config WHERE guild_id = ?", (guild_id,))
    result = cursor.fetchone()
    conn.close()
    
    if not result or not result[0]:
        return  # Log kanalı ayarlanmamışsa çık
    
    log_channel_id = result[0]
    log_channel = bot.get_channel(log_channel_id)
    
    if not log_channel:
        return  # Log kanalı bulunamadıysa çık
    
    # Log mesajı oluştur
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.datetime.now(TURKEY_TIMEZONE)
    )
    
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    
    embed.set_footer(text=f"HydRaboN Ticket Sistemi")
    
    try:
        await log_channel.send(embed=embed)
    except Exception as e:
        print(f"Log gönderilemedi: {e}")

# Rol ekleme komutu
@bot.tree.command(name="rol_ekle", description="Ticket sistemine yeni bir yetkili rolü ekler")
@app_commands.default_permissions(administrator=True)
async def add_role(interaction: discord.Interaction, rol: discord.Role):
    await interaction.response.defer(ephemeral=True)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Mevcut yapılandırmayı kontrol et
    cursor.execute("SELECT admin_role_ids FROM config WHERE guild_id = ?", (interaction.guild.id,))
    result = cursor.fetchone()
    
    if not result:
        await interaction.followup.send("Ticket sistemi henüz kurulmadı. Önce `/setup` komutunu kullanın.", ephemeral=True)
        conn.close()
        return
    
    # Mevcut roller
    admin_role_ids = result[0].split(',') if ',' in result[0] else [result[0]]
    
    # Rol zaten ekli mi kontrol et
    if str(rol.id) in admin_role_ids:
        await interaction.followup.send(f"{rol.mention} zaten yetkili rollerine eklenmiş.", ephemeral=True)
        conn.close()
        return
    
    # Yeni rolü ekle
    admin_role_ids.append(str(rol.id))
    
    # Güncelle
    cursor.execute(
        "UPDATE config SET admin_role_ids = ? WHERE guild_id = ?",
        (','.join(admin_role_ids), interaction.guild.id)
    )
    
    conn.commit()
    conn.close()
    
    await interaction.followup.send(f"{rol.mention} yetkili rollerine eklendi.", ephemeral=True)
    
    # Log kaydı
    await log_action(
        interaction.guild.id,
        "Rol Eklendi",
        f"Ticket sistemine yeni yetkili rolü eklendi.",
        discord.Color.blue(),
        [
            ("Rol", rol.mention, True),
            ("Ekleyen", interaction.user.mention, True)
        ]
    )

# Rol çıkarma komutu
@bot.tree.command(name="rol_cikar", description="Ticket sisteminden bir yetkili rolünü çıkarır")
@app_commands.default_permissions(administrator=True)
async def remove_role(interaction: discord.Interaction, rol: discord.Role):
    await interaction.response.defer(ephemeral=True)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Mevcut yapılandırmayı kontrol et
    cursor.execute("SELECT admin_role_ids FROM config WHERE guild_id = ?", (interaction.guild.id,))
    result = cursor.fetchone()
    
    if not result:
        await interaction.followup.send("Ticket sistemi henüz kurulmadı. Önce `/setup` komutunu kullanın.", ephemeral=True)
        conn.close()
        return
    
    # Mevcut roller
    admin_role_ids = result[0].split(',') if ',' in result[0] else [result[0]]
    
    # Rol var mı kontrol et
    if str(rol.id) not in admin_role_ids:
        await interaction.followup.send(f"{rol.mention} yetkili rollerinde bulunamadı.", ephemeral=True)
        conn.close()
        return
    
    # Rolü çıkar
    admin_role_ids.remove(str(rol.id))
    
    # En az bir rol olmalı
    if not admin_role_ids:
        await interaction.followup.send("En az bir yetkili rolü olmalıdır.", ephemeral=True)
        conn.close()
        return
    
    # Güncelle
    cursor.execute(
        "UPDATE config SET admin_role_ids = ? WHERE guild_id = ?",
        (','.join(admin_role_ids), interaction.guild.id)
    )
    
    conn.commit()
    conn.close()
    
    await interaction.followup.send(f"{rol.mention} yetkili rollerinden çıkarıldı.", ephemeral=True)
    
    # Log kaydı
    await log_action(
        interaction.guild.id,
        "Rol Çıkarıldı",
        f"Ticket sisteminden yetkili rolü çıkarıldı.",
        discord.Color.orange(),
        [
            ("Rol", rol.mention, True),
            ("Çıkaran", interaction.user.mention, True)
        ]
    )

# Ayarları görüntüleme komutu
@bot.tree.command(name="ayarlar", description="Ticket sistemi ayarlarını gösterir")
@app_commands.default_permissions(administrator=True)
async def settings(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Yapılandırmayı kontrol et
    cursor.execute("SELECT ticket_channel_id, admin_role_ids, log_channel_id, ticket_count FROM config WHERE guild_id = ?", (interaction.guild.id,))
    result = cursor.fetchone()
    
    if not result:
        await interaction.followup.send("Ticket sistemi henüz kurulmadı. Önce `/setup` komutunu kullanın.", ephemeral=True)
        conn.close()
        return
    
    ticket_channel_id, admin_role_ids, log_channel_id, ticket_count = result
    
    embed = discord.Embed(
        title="Ticket Sistemi Ayarları",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.now(TURKEY_TIMEZONE)
    )
    
    # Ticket kanalı
    ticket_channel = interaction.guild.get_channel(ticket_channel_id)
    embed.add_field(
        name="Ticket Kanalı",
        value=ticket_channel.mention if ticket_channel else "Bulunamadı",
        inline=False
    )
    
    # Yetkili rolleri
    admin_roles = []
    for role_id in admin_role_ids.split(',') if ',' in admin_role_ids else [admin_role_ids]:
        try:
            role = interaction.guild.get_role(int(role_id))
            if role:
                admin_roles.append(role.mention)
        except (ValueError, AttributeError):
            continue
    
    embed.add_field(
        name="Yetkili Rolleri",
        value=', '.join(admin_roles) if admin_roles else "Bulunamadı",
        inline=False
    )
    
    # Log kanalı
    if log_channel_id:
        log_channel = interaction.guild.get_channel(log_channel_id)
        embed.add_field(
            name="Log Kanalı",
            value=log_channel.mention if log_channel else "Bulunamadı",
            inline=False
        )
    else:
        embed.add_field(
            name="Log Kanalı",
            value="Ayarlanmadı",
            inline=False
        )
    
    # Ticket sayısı
    embed.add_field(
        name="Toplam Açılan Ticket Sayısı",
        value=str(ticket_count),
        inline=False
    )
    
    conn.close()
    
    await interaction.followup.send(embed=embed, ephemeral=True)

# İstatistik komutu
@bot.tree.command(name="istatistik", description="Ticket sistemi istatistiklerini gösterir")
@app_commands.default_permissions(administrator=True)
async def statistics(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Toplam ticket sayısı
    cursor.execute("SELECT COUNT(*) FROM tickets")
    total_tickets = cursor.fetchone()[0]
    
    # Açık ticket sayısı
    cursor.execute("SELECT COUNT(*) FROM tickets WHERE status = 'open'")
    open_tickets = cursor.fetchone()[0]
    
    # Kapalı ticket sayısı
    cursor.execute("SELECT COUNT(*) FROM tickets WHERE status = 'closed'")
    closed_tickets = cursor.fetchone()[0]
    
    # En çok ticket açan kullanıcılar
    cursor.execute("""
    SELECT user_id, COUNT(*) as count 
    FROM tickets 
    GROUP BY user_id 
    ORDER BY count DESC 
    LIMIT 5
    """)
    top_users = cursor.fetchall()
    
    # En çok yardım eden yetkililer
    cursor.execute("""
    SELECT admin_id, COUNT(*) as count 
    FROM ticket_helpers 
    GROUP BY admin_id 
    ORDER BY count DESC 
    LIMIT 5
    """)
    top_admins = cursor.fetchall()
    
    conn.close()
    
    embed = discord.Embed(
        title="Ticket Sistemi İstatistikleri",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.now(TURKEY_TIMEZONE)
    )
    
    embed.add_field(name="Toplam Ticket", value=str(total_tickets), inline=True)
    embed.add_field(name="Açık Ticket", value=str(open_tickets), inline=True)
    embed.add_field(name="Kapalı Ticket", value=str(closed_tickets), inline=True)
    
    # En çok ticket açan kullanıcılar
    top_users_str = ""
    for i, (user_id, count) in enumerate(top_users, 1):
        try:
            user = await bot.fetch_user(user_id)
            top_users_str += f"{i}. {user.mention}: {count} ticket\n"
        except:
            top_users_str += f"{i}. ID: {user_id}: {count} ticket\n"
    
    if top_users_str:
        embed.add_field(name="En Çok Ticket Açanlar", value=top_users_str, inline=False)
    
    # En çok yardım eden yetkililer
    top_admins_str = ""
    for i, (admin_id, count) in enumerate(top_admins, 1):
        try:
            admin = await bot.fetch_user(admin_id)
            top_admins_str += f"{i}. {admin.mention}: {count} ticket\n"
        except:
            top_admins_str += f"{i}. ID: {admin_id}: {count} ticket\n"
    
    if top_admins_str:
        embed.add_field(name="En Çok Yardım Eden Yetkililer", value=top_admins_str, inline=False)
    
    await interaction.followup.send(embed=embed)

# Yeni ticket oluşturma fonksiyonu
async def create_new_ticket(interaction: discord.Interaction, subject: str, description: str):
    user_id = interaction.user.id
    guild = interaction.guild
    
    # Kullanıcının açık bir ticket'ı var mı kontrol et
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT channel_id FROM tickets WHERE user_id = ? AND status = 'open'", (user_id,))
    existing_ticket = cursor.fetchone()
    
    if existing_ticket:
        channel = guild.get_channel(existing_ticket[0])
        if channel:
            conn.close()
            return None  # Zaten açık bir ticket var
    
    # Yapılandırma bilgilerini al
    cursor.execute("SELECT admin_role_ids, ticket_count, ticket_channel_id FROM config WHERE guild_id = ?", (guild.id,))
    config = cursor.fetchone()
    
    if not config:
        conn.close()
        return None  # Yapılandırma bulunamadı
    
    admin_role_ids = config[0].split(',') if ',' in config[0] else [config[0]]
    ticket_count = config[1] + 1
    ticket_channel_id = config[2]
    
    # Yeni ticket sayısını güncelle
    cursor.execute("UPDATE config SET ticket_count = ? WHERE guild_id = ?", (ticket_count, guild.id))
    
    # Ticket kanalı oluştur
    ticket_id = f"ticket-{ticket_count:04d}"
    
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    
    for role_id in admin_role_ids:
        try:
            role = guild.get_role(int(role_id))
            if role:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        except ValueError:
            continue
    
    # Setup kanalının kategorisini kullan
    ticket_channel = guild.get_channel(ticket_channel_id)
    category = ticket_channel.category if ticket_channel and ticket_channel.category else None
    
    # Kategori yoksa varsayılan olarak "Tickets" kategorisini oluştur
    if not category:
        category = discord.utils.get(guild.categories, name="Tickets")
        if not category:
            category = await guild.create_category("Tickets")
    
    channel = await guild.create_text_channel(
        name=f"ticket-{interaction.user.name}",
        category=category,
        overwrites=overwrites,
        topic=f"Konu: {subject} | Ticket Sahibi: {interaction.user.mention} | ID: {user_id}"
    )
    
    # Ticket'ı veritabanına kaydet
    cursor.execute(
        "INSERT INTO tickets (ticket_id, user_id, channel_id, status, subject, description, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ticket_id, user_id, channel.id, "open", subject, description, datetime.datetime.now(TURKEY_TIMEZONE))
    )
    
    conn.commit()
    conn.close()
    
    # Ticket açılış mesajı
    embed = discord.Embed(
        title=f"Ticket: {ticket_id}",
        description=f"Merhaba {interaction.user.mention}, ticket'ınız oluşturuldu.\nLütfen aşağıdaki bilgilere göz atın ve ekibimiz en kısa sürede size yardımcı olacak.",
        color=discord.Color.green(),
        timestamp=datetime.datetime.now(TURKEY_TIMEZONE)
    )
    
    embed.add_field(name="📋 Konu", value=subject, inline=False)
    embed.add_field(name="📝 Açıklama", value=description, inline=False)
    embed.set_footer(text=f"HydRaboN Ticket Sistemi • {guild.name}")
    
    # Ticket işlem butonları
    ticket_actions = TicketActionsView()
    
    # Mesajı gönder
    await channel.send(embed=embed, view=ticket_actions)
    
    # Log kaydı
    await log_action(
        guild.id,
        "Ticket Oluşturuldu",
        f"Yeni bir ticket ({ticket_id}) oluşturuldu.",
        discord.Color.green(),
        [
            ("Kullanıcı", f"{interaction.user.mention} ({interaction.user.id})", True),
            ("Kanal", channel.mention, True),
            ("Konu", subject, False)
        ]
    )
    
    return channel

# Bot token
TOKEN = os.getenv('DISCORD_TOKEN')  # .env dosyasından token alınır

if not TOKEN:
    print("HATA: DISCORD_TOKEN bulunamadı! Lütfen .env dosyasında tanımlayın veya çevresel değişken olarak ayarlayın.")
else:
    bot.run(TOKEN)
