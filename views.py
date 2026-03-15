import discord
from discord import ui
import datetime

from config import YETKILI_ROLLERI, TICKET_KATEGORILERI, TURKEY_TIMEZONE
from database import get_db_connection
from utils import is_admin, get_admin_role_ids, create_new_ticket, close_ticket, create_transcript
from utils import log_action, update_ticket_permissions


# Ticket kategori seçim dropdown'u
class TicketCategorySelect(ui.Select):
    def __init__(self):
        options = []
        for key, kategori in TICKET_KATEGORILERI.items():
            options.append(
                discord.SelectOption(
                    label=kategori["label"],
                    value=key,
                    description=kategori["aciklama"],
                    emoji=kategori["emoji"],
                )
            )

        super().__init__(
            placeholder="Destek talebi oluşturmak için bir kategori seçin...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ticket_category_select",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        category_key = self.values[0]
        channel = await create_new_ticket(interaction, category_key)

        if channel:
            await interaction.followup.send(
                f"Ticket'ınız oluşturuldu: {channel.mention}", ephemeral=True
            )
        else:
            await interaction.followup.send(
                "Ticket oluşturulurken bir hata oluştu veya zaten açık bir ticket'ınız var.",
                ephemeral=True,
            )


# Ticket select menu'yü barındıran view
class TicketSelectView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketCategorySelect())


# Ticket içi aksiyon butonları
class TicketActionsView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Ticket'ı Kapat",
        style=discord.ButtonStyle.danger,
        emoji="\U0001f512",
        custom_id="close_ticket",
    )
    async def close_ticket_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        transcript = await create_transcript(interaction.channel)
        success = await close_ticket(interaction, transcript)
        if not success:
            await interaction.followup.send(
                "Ticket kapatılırken bir hata oluştu.", ephemeral=True
            )

    @discord.ui.button(
        label="Yardım Et",
        style=discord.ButtonStyle.primary,
        emoji="\U0001f44b",
        custom_id="join_ticket",
    )
    async def join_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        channel = interaction.channel

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT ticket_id, user_id FROM tickets WHERE channel_id = ? AND status = 'open'",
            (channel.id,),
        )
        ticket = cursor.fetchone()

        if not ticket:
            await interaction.followup.send(
                "Bu kanal bir ticket değil veya kapatılmış.", ephemeral=True
            )
            conn.close()
            return

        ticket_id, ticket_owner_id = ticket

        if not is_admin(interaction.user):
            await interaction.followup.send(
                "Bu butonu kullanmak için yetkiniz yok.", ephemeral=True
            )
            conn.close()
            return

        # Kullanıcı zaten yardımcı olarak eklenmiş mi
        cursor.execute(
            "SELECT * FROM ticket_helpers WHERE ticket_id = ? AND admin_id = ?",
            (ticket_id, interaction.user.id),
        )
        helper = cursor.fetchone()

        if helper:
            await interaction.followup.send(
                "Bu ticket'a zaten yardımcı olarak eklendiniz.", ephemeral=True
            )
            conn.close()
            return

        # Yardımcı olarak ekle
        cursor.execute(
            "INSERT INTO ticket_helpers (ticket_id, admin_id, joined_at) VALUES (?, ?, ?)",
            (ticket_id, interaction.user.id, datetime.datetime.now(TURKEY_TIMEZONE)),
        )

        conn.commit()
        conn.close()

        # İzinleri düzenle
        await update_ticket_permissions(
            channel, interaction.guild, int(ticket_owner_id), interaction.user.id
        )

        embed = discord.Embed(
            title="Yeni Yetkili",
            description=f"{interaction.user.mention} bu ticket'a yardımcı olarak katıldı.",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(TURKEY_TIMEZONE),
        )

        await interaction.followup.send(embed=embed)

        await log_action(
            interaction.guild.id,
            "Yetkili Katıldı",
            f"Bir yetkili ticket'a ({ticket_id}) katıldı.",
            discord.Color.green(),
            [("Yetkili", f"{interaction.user.mention} ({interaction.user.id})", True)],
        )

    @discord.ui.button(
        label="Yetkili Ekle",
        style=discord.ButtonStyle.success,
        emoji="\U0001f465",
        custom_id="add_admin",
    )
    async def add_admin(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        channel = interaction.channel

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT ticket_id, user_id FROM tickets WHERE channel_id = ? AND status = 'open'",
            (channel.id,),
        )
        ticket = cursor.fetchone()

        if not ticket:
            await interaction.followup.send(
                "Bu kanal bir ticket değil veya kapatılmış.", ephemeral=True
            )
            conn.close()
            return

        ticket_id, ticket_owner_id = ticket

        # Kullanıcının halihazırda yardımcı olup olmadığını kontrol et
        cursor.execute(
            "SELECT * FROM ticket_helpers WHERE ticket_id = ? AND admin_id = ?",
            (ticket_id, interaction.user.id),
        )
        helper = cursor.fetchone()

        if not helper:
            await interaction.followup.send(
                "Bu ticket'ta yetkili değilsiniz. Önce 'Yardım Et' butonunu kullanmalısınız.",
                ephemeral=True,
            )
            conn.close()
            return

        # Halihazırda bu ticket'a yardım eden yetkililer
        cursor.execute("SELECT admin_id FROM ticket_helpers WHERE ticket_id = ?", (ticket_id,))
        existing_helpers = [row[0] for row in cursor.fetchall()]

        conn.close()

        # Yetkili listesini oluştur
        guild = interaction.guild
        admin_options = []
        admin_role_ids = get_admin_role_ids()

        for role_id in admin_role_ids:
            role = guild.get_role(role_id)
            if role:
                for member in role.members:
                    if member.id != interaction.user.id and member.id not in existing_helpers:
                        if not any(option.value == str(member.id) for option in admin_options):
                            admin_options.append(
                                discord.SelectOption(
                                    label=member.display_name,
                                    value=str(member.id),
                                    description=f"ID: {member.id}",
                                )
                            )

        if not admin_options:
            await interaction.followup.send(
                "Eklenebilecek başka yetkili bulunamadı.", ephemeral=True
            )
            return

        modal = AdminSelectModal(admin_options, ticket_id, int(ticket_owner_id))
        await interaction.followup.send(
            "Lütfen eklemek istediğiniz yetkiliyi seçin:", view=modal, ephemeral=True
        )


# Yetkili ekleme dropdown view
class AdminSelectModal(ui.View):
    def __init__(self, admin_options, ticket_id, ticket_owner_id):
        super().__init__(timeout=180)
        self.add_item(AdminSelectDropdown(admin_options, ticket_id, ticket_owner_id))


# Yetkili seçme dropdown'u
class AdminSelectDropdown(ui.Select):
    def __init__(self, admin_options, ticket_id, ticket_owner_id):
        self.ticket_id = ticket_id
        self.ticket_owner_id = ticket_owner_id

        super().__init__(
            placeholder="Eklemek istediğiniz yetkiliyi seçin...",
            min_values=1,
            max_values=1,
            options=admin_options,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        selected_admin_id = int(self.values[0])

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT channel_id FROM tickets WHERE ticket_id = ?", (self.ticket_id,)
        )
        result = cursor.fetchone()

        if not result:
            await interaction.followup.send("Ticket bilgileri bulunamadı.", ephemeral=True)
            conn.close()
            return

        channel_id = result[0]

        # Yetkili zaten eklenmiş mi
        cursor.execute(
            "SELECT * FROM ticket_helpers WHERE ticket_id = ? AND admin_id = ?",
            (self.ticket_id, selected_admin_id),
        )
        helper = cursor.fetchone()

        if helper:
            await interaction.followup.send(
                "Bu yetkili zaten ticket'a eklenmiş.", ephemeral=True
            )
            conn.close()
            return

        # Yetkiliyi ekle
        cursor.execute(
            "INSERT INTO ticket_helpers (ticket_id, admin_id, joined_at) VALUES (?, ?, ?)",
            (self.ticket_id, selected_admin_id, datetime.datetime.now(TURKEY_TIMEZONE)),
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
            timestamp=datetime.datetime.now(TURKEY_TIMEZONE),
        )

        await channel.send(embed=embed)

        await log_action(
            interaction.guild.id,
            "Yetkili Eklendi",
            f"Bir yetkili ticket'a ({self.ticket_id}) eklendi.",
            discord.Color.green(),
            [
                ("Eklenen Yetkili", f"{selected_member.mention} ({selected_admin_id})", True),
                ("Ekleyen Yetkili", f"{interaction.user.mention} ({interaction.user.id})", True),
            ],
        )

        await interaction.followup.send(
            f"{selected_member.mention} ticket'a başarıyla eklendi.", ephemeral=True
        )
