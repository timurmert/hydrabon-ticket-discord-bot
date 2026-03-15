import discord
from discord import app_commands
import datetime

from config import YETKILI_ROLLERI, TURKEY_TIMEZONE
from database import get_db_connection
from views import TicketSelectView


def setup_commands(bot):
    """Bot'a slash komutlarını ekler."""

    @bot.tree.command(name="setup", description="Ticket sistemini kurar")
    @app_commands.default_permissions(administrator=True)
    async def setup(
        interaction: discord.Interaction,
        kanal: discord.TextChannel,
        log_kanal: discord.TextChannel = None,
    ):
        await interaction.response.defer(ephemeral=True)

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM config WHERE guild_id = ?", (interaction.guild.id,))
        existing_config = cursor.fetchone()

        if existing_config:
            cursor.execute(
                "UPDATE config SET ticket_channel_id = ?, log_channel_id = ? WHERE guild_id = ?",
                (kanal.id, log_kanal.id if log_kanal else None, interaction.guild.id),
            )
        else:
            cursor.execute(
                "INSERT INTO config (guild_id, ticket_channel_id, log_channel_id, ticket_count) VALUES (?, ?, ?, ?)",
                (interaction.guild.id, kanal.id, log_kanal.id if log_kanal else None, 0),
            )

        conn.commit()
        conn.close()

        # Ticket embed'i ve select menu'yü gönder
        embed = discord.Embed(
            title="\U0001f4cb HydRaboN Ticket Sistemi",
            description=(
                "Teknik sorun, \u015fikayet, \u00f6neri veya ba\u015fvurular\u0131n\u0131z i\u00e7in destek talebi olu\u015fturabilirsiniz.\n\n"
                "\u2705 **H\u0131zl\u0131 Yan\u0131t**\n"
                "\U0001f465 **\u00d6zel Destek**\n"
                "\U0001f512 **G\u00fcvenli \u0130leti\u015fim**\n\n"
                "A\u015fa\u011f\u0131daki men\u00fcden kategori se\u00e7erek destek talebi olu\u015fturabilirsiniz."
            ),
            color=discord.Color.brand_green(),
        )
        embed.set_thumbnail(
            url="https://cdn.discordapp.com/attachments/1109802773839134772/1118864108351655936/HydRaboN.png"
        )
        embed.set_footer(
            text=f"HydRaboN Ticket Sistemi \u2022 {interaction.guild.name}",
            icon_url=interaction.guild.icon.url if interaction.guild.icon else None,
        )

        await kanal.send(embed=embed, view=TicketSelectView())

        log_mesaj = "Ticket sistemi ba\u015far\u0131yla kuruldu."
        if log_kanal:
            log_mesaj += f" Log kanal\u0131: {log_kanal.mention}"

        await interaction.followup.send(log_mesaj, ephemeral=True)

    @bot.tree.command(name="ayarlar", description="Ticket sistemi ayarlar\u0131n\u0131 g\u00f6sterir")
    @app_commands.default_permissions(administrator=True)
    async def settings(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT ticket_channel_id, log_channel_id, ticket_count FROM config WHERE guild_id = ?",
            (interaction.guild.id,),
        )
        result = cursor.fetchone()

        if not result:
            await interaction.followup.send(
                "Ticket sistemi hen\u00fcz kurulmad\u0131. \u00d6nce `/setup` komutunu kullan\u0131n.", ephemeral=True
            )
            conn.close()
            return

        ticket_channel_id, log_channel_id, ticket_count = result
        conn.close()

        embed = discord.Embed(
            title="Ticket Sistemi Ayarlar\u0131",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now(TURKEY_TIMEZONE),
        )

        # Ticket kanal\u0131
        ticket_channel = interaction.guild.get_channel(ticket_channel_id)
        embed.add_field(
            name="Ticket Kanal\u0131",
            value=ticket_channel.mention if ticket_channel else "Bulunamad\u0131",
            inline=False,
        )

        # Yetkili rolleri (config.py'den)
        admin_roles = []
        for role_name, role_id in YETKILI_ROLLERI.items():
            role = interaction.guild.get_role(role_id)
            if role:
                admin_roles.append(f"{role.mention} ({role_name})")

        embed.add_field(
            name="Yetkili Rolleri",
            value="\n".join(admin_roles) if admin_roles else "Bulunamad\u0131",
            inline=False,
        )

        # Log kanal\u0131
        if log_channel_id:
            log_channel = interaction.guild.get_channel(log_channel_id)
            embed.add_field(
                name="Log Kanal\u0131",
                value=log_channel.mention if log_channel else "Bulunamad\u0131",
                inline=False,
            )
        else:
            embed.add_field(name="Log Kanal\u0131", value="Ayarlanmad\u0131", inline=False)

        # Ticket say\u0131s\u0131
        embed.add_field(
            name="Toplam A\u00e7\u0131lan Ticket Say\u0131s\u0131",
            value=str(ticket_count),
            inline=False,
        )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @bot.tree.command(name="istatistik", description="Ticket sistemi istatistiklerini g\u00f6sterir")
    @app_commands.default_permissions(administrator=True)
    async def statistics(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM tickets")
        total_tickets = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM tickets WHERE status = 'open'")
        open_tickets = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM tickets WHERE status = 'closed'")
        closed_tickets = cursor.fetchone()[0]

        # En \u00e7ok ticket a\u00e7an kullan\u0131c\u0131lar
        cursor.execute("""
        SELECT user_id, COUNT(*) as count
        FROM tickets
        GROUP BY user_id
        ORDER BY count DESC
        LIMIT 5
        """)
        top_users = cursor.fetchall()

        # En \u00e7ok yard\u0131m eden yetkililer
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
            title="Ticket Sistemi \u0130statistikleri",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now(TURKEY_TIMEZONE),
        )

        embed.add_field(name="Toplam Ticket", value=str(total_tickets), inline=True)
        embed.add_field(name="A\u00e7\u0131k Ticket", value=str(open_tickets), inline=True)
        embed.add_field(name="Kapal\u0131 Ticket", value=str(closed_tickets), inline=True)

        # En \u00e7ok ticket a\u00e7an kullan\u0131c\u0131lar
        top_users_str = ""
        for i, (user_id, count) in enumerate(top_users, 1):
            try:
                user = await bot.fetch_user(user_id)
                top_users_str += f"{i}. {user.mention}: {count} ticket\n"
            except Exception:
                top_users_str += f"{i}. ID: {user_id}: {count} ticket\n"

        if top_users_str:
            embed.add_field(name="En \u00c7ok Ticket A\u00e7anlar", value=top_users_str, inline=False)

        # En \u00e7ok yard\u0131m eden yetkililer
        top_admins_str = ""
        for i, (admin_id, count) in enumerate(top_admins, 1):
            try:
                admin = await bot.fetch_user(admin_id)
                top_admins_str += f"{i}. {admin.mention}: {count} ticket\n"
            except Exception:
                top_admins_str += f"{i}. ID: {admin_id}: {count} ticket\n"

        if top_admins_str:
            embed.add_field(
                name="En \u00c7ok Yard\u0131m Eden Yetkililer", value=top_admins_str, inline=False
            )

        await interaction.followup.send(embed=embed)
