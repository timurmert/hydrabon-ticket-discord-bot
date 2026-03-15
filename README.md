# HydRaboN Discord Ticket Bot

Bu bot, Discord sunucunuzda destek talebi (ticket) sistemi kurmanızı sağlar. Kullanıcılar belirli bir kanaldan ticket açabilir ve yetkililer bu ticket'lar üzerinden destek sunabilir.

## Özellikler

- 🎫 Buton ile kolay ticket oluşturma
- 🔒 Ticket'ları güvenli bir şekilde kapatma
- 📊 Ticket istatistikleri görüntüleme
- 👮 Yetkili yardım sistemi (buton üzerinden)
- 📂 SQLite veritabanı ile ticket kayıtları
- 📋 Ticket açarken konu ve açıklama alanı
- 📱 Tamamen Türkçe arayüz

## Kurulum

1. Repoyu klonlayın veya indirin
2. Gerekli paketleri yükleyin:
   ```
   pip install -r requirements.txt
   ```
3. `.env` dosyasını düzenleyin ve Discord botunuzun token'ını ekleyin:
   ```
   DISCORD_TOKEN=BOT_TOKEN_BURAYA
   ```
4. Botu çalıştırın:
   ```
   python main.py
   ```

## Komutlar

- `/setup <kanal> <yetkili_rol> [log_kanal]` - Ticket sistemini ayarlar
- `/rol_ekle <rol>` - Ticket sistemine yeni bir yetkili rolü ekler
- `/rol_cikar <rol>` - Ticket sisteminden bir yetkili rolünü çıkarır
- `/ayarlar` - Ticket sistemi ayarlarını gösterir
- `/istatistik` - Ticket sistemi istatistiklerini gösterir

## Ticket Özellikleri

- **Ticket Oluşturma**: Kullanıcılar konu ve açıklama girerek ticket oluşturabilir
- **Ticket Kapatma**: Ticket'lar yetkili veya açan kişi tarafından kolayca kapatılabilir
- **Yardım Etme Butonu**: Yetkililer ticket'a "Yardım Et" butonu ile katılabilir
- **Ticket Transcript**: Kapatılan ticket'ların tam geçmişi MD formatında log kanalına kaydedilir
- **Yetkili Yardım Takibi**: Hangi yetkililerin hangi ticket'lara yardım ettiği takip edilir

## Gereksinimler

- Python 3.8+
- discord.py 2.0.0+
- python-dotenv

## Bakım ve Geliştirme

- `main.py` - Ana bot kodu
- `ticket_database.db` - SQLite veritabanı (otomatik oluşturulur)

---

Proje: HydRaboN Discord Ticket Bot 