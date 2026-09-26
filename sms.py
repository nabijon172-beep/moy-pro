"""SMS eslatma yuborish. Hozircha SIMULYATSIYA rejimida: haqiqiy SMS ketmaydi,
faqat konsolga "yuborildi" deb yoziladi va shu tarzda qaytariladi — shu bilan
butun tizimni (kimga, qachon, qanday matn) SMS provayder tanlamasdan sinash mumkin.

Haqiqiy SMS yuborishni yoqish uchun:
  1) Eskiz.uz saytida (https://eskiz.uz) akkaunt oching
  2) Pastda ESKIZ_EMAIL va ESKIZ_PAROL ni to'ldiring
  3) SMS_YOQILGAN = True qiling
  4) requirements.txt ga "requests" qatorini qo'shing (agar hali yo'q bo'lsa) va serverda qayta o'rnating
"""
import os
import requests

SMS_YOQILGAN = os.environ.get("SMS_YOQILGAN", "0") == "1"
ESKIZ_EMAIL = os.environ.get("ESKIZ_EMAIL", "")
ESKIZ_PAROL = os.environ.get("ESKIZ_PAROL", "")
ESKIZ_NOM = os.environ.get("ESKIZ_NOM", "4546")


def matn_tayyorla(ism, keyingi_sana, keyingi_km=None):
    salom = f"Hurmatli {ism}, " if ism else "Hurmatli mijoz, "
    qism = f" ({keyingi_km} km atrofida)" if keyingi_km else ""
    return (f"{salom}avtomobilingizda moy almashtirish muddati yaqinlashmoqda "
            f"(taxminan {keyingi_sana}{qism}). Xizmatga yozilish uchun bog'laning.")


def _eskiz_yubor(telefon, matn):
    tok = requests.post("https://notify.eskiz.uz/api/auth/login",
                        data={"email": ESKIZ_EMAIL, "password": ESKIZ_PAROL}, timeout=15)
    tok.raise_for_status()
    token = tok.json()["data"]["token"]
    raqam = "".join(ch for ch in telefon if ch.isdigit())
    javob = requests.post("https://notify.eskiz.uz/api/message/sms/send",
                          headers={"Authorization": f"Bearer {token}"},
                          data={"mobile_phone": raqam, "message": matn, "from": ESKIZ_NOM}, timeout=15)
    javob.raise_for_status()
    return javob.json()


def yubor(telefon, matn):
    """(xabar, muvaffaqiyatli) qaytaradi."""
    if not telefon:
        return "Telefon raqami yo'q.", False
    if not SMS_YOQILGAN:
        print(f"[SMS SIMULYATSIYA] {telefon} -> {matn}")
        return f"(simulyatsiya) yuborilgan bo'lardi", True
    if not ESKIZ_EMAIL or not ESKIZ_PAROL:
        return "SMS_YOQILGAN=1, lekin ESKIZ_EMAIL/ESKIZ_PAROL to'ldirilmagan.", False
    try:
        _eskiz_yubor(telefon, matn)
        return "Yuborildi", True
    except Exception as xato:
        return f"Xatolik: {xato}", False
