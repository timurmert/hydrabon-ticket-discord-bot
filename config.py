import pytz

# Türkiye zaman dilimi
TURKEY_TIMEZONE = pytz.timezone('Europe/Istanbul')

# Yetkili rolleri (Discord Role ID'leri)
YETKILI_ROLLERI = {
    "STAJYER": 1163918714081644554,
    "ASİSTAN": 1200919832393154680,
    "MODERATÖR": 1163918107501412493,
    "KIDEMLİ MODERATÖR": 1460021463607152703,
    "ADMİN": 1163918130192580608,
    "YÖNETİM KURULU ADAYLARI": 1412843482980290711,
    "YÖNETİM KURULU ÜYELERİ": 1029089731314720798,
    "YÖNETİM KURULU BAŞKANI": 1029089727061692522,
    "KURUCU YARDIMCISI": 1459975838853238897,
    "KURUCU": 1029089723110674463,
}

# Ticket kategorileri
TICKET_KATEGORILERI = {
    "teknik-destek": {
        "label": "Teknik Destek",
        "kisaltma": "TD",
        "emoji": "\U0001f527",
        "aciklama": "Teknik sorunlar için destek talebi",
    },
    "sikayet": {
        "label": "Şikayet",
        "kisaltma": "SK",
        "emoji": "\u26a0\ufe0f",
        "aciklama": "Şikayet bildirimi",
    },
    "oneri": {
        "label": "Öneri",
        "kisaltma": "ON",
        "emoji": "\U0001f4a1",
        "aciklama": "Öneri ve geri bildirim",
    },
    "genel-destek": {
        "label": "Genel Destek",
        "kisaltma": "GD",
        "emoji": "\U0001f4cb",
        "aciklama": "Genel destek talepleri",
    },
    "basvuru": {
        "label": "Başvuru",
        "kisaltma": "BV",
        "emoji": "\U0001f4dd",
        "aciklama": "Başvuru işlemleri",
    },
}

# Otomatik kapatma ayarları
INACTIVITY_HOURS = 24
CHECK_INTERVAL_HOURS = 1
