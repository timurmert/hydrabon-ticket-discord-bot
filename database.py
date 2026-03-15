import sqlite3
import datetime


# SQLite datetime dönüştürücüleri
def adapt_datetime(dt):
    return dt.isoformat()


def convert_datetime(s):
    try:
        return datetime.datetime.fromisoformat(s.decode())
    except (AttributeError, ValueError):
        return datetime.datetime.fromisoformat(s)


# SQLite'a datetime dönüştürücüleri kaydet
sqlite3.register_adapter(datetime.datetime, adapt_datetime)
sqlite3.register_converter("timestamp", convert_datetime)

DB_PATH = "ticket_database.db"


def get_db_connection():
    return sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)


def create_database():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Ticket tablosu
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tickets (
        ticket_id TEXT PRIMARY KEY,
        user_id INTEGER,
        channel_id INTEGER,
        status TEXT,
        category TEXT,
        created_at timestamp,
        closed_at timestamp
    )
    """)

    # Admin yardım tablosu
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ticket_helpers (
        ticket_id TEXT,
        admin_id INTEGER,
        joined_at timestamp,
        FOREIGN KEY (ticket_id) REFERENCES tickets(ticket_id)
    )
    """)

    # Yapılandırma tablosu (admin_role_ids kaldırıldı)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS config (
        guild_id INTEGER PRIMARY KEY,
        ticket_channel_id INTEGER,
        log_channel_id INTEGER,
        ticket_count INTEGER DEFAULT 0
    )
    """)

    conn.commit()
    conn.close()
