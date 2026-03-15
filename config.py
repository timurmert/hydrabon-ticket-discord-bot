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
    "genel-destek": {
        "label": "Genel Destek",
        "kisaltma": "GD",
        "emoji": "\U0001f4cb",
        "aciklama": "Genel sorular ve destek talepleri",
    },
    "discord": {
        "label": "Discord",
        "kisaltma": "DC",
        "emoji": "\U0001f4ac",
        "aciklama": "Discord sunucusu ile ilgili talepler",
    },
    "arge-yazilim": {
        "label": "AR-GE / Yaz\u0131l\u0131m",
        "kisaltma": "AY",
        "emoji": "\U0001f4bb",
        "aciklama": "AR-GE ve yaz\u0131l\u0131m ile ilgili talepler",
    },
    "reklam": {
        "label": "Reklam",
        "kisaltma": "RK",
        "emoji": "\U0001f4e2",
        "aciklama": "Reklam talepleri ve ba\u015fvurular\u0131",
    },
    "sponsorluk": {
        "label": "Sponsorluk & \u0130\u015f Birli\u011fi",
        "kisaltma": "SB",
        "emoji": "\U0001f91d",
        "aciklama": "Sponsorluk ve i\u015f birli\u011fi teklifleri",
    },
    "diger": {
        "label": "Di\u011fer",
        "kisaltma": "DG",
        "emoji": "\U0001f4cc",
        "aciklama": "Di\u011fer konulardaki talepler",
    },
}

# Otomatik kapatma ayarları
INACTIVITY_HOURS = 24
CHECK_INTERVAL_HOURS = 1
