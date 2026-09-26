import sqlite3
from datetime import datetime, timedelta
from fastapi import HTTPException, Request
from pydantic import BaseModel
from server import app, db, ega, norm

import sms

SMS_QAYTA_KUN = 7  # bir mijozga necha kunda bir marta eslatma yuborish mumkin

with db() as c:
    try:
        c.execute("alter table mijoz add column oxirgi_sms text")
    except sqlite3.OperationalError:
        pass  # ustun allaqachon bor


def sms_kerak(c, kun=14):
    chegara = (datetime.now() + timedelta(days=kun)).strftime("%Y-%m-%d")
    qayta = (datetime.now() - timedelta(days=SMS_QAYTA_KUN)).strftime("%Y-%m-%d")
    return [dict(r) for r in c.execute("""
        select x.raqam, x.keyingi_km, x.keyingi_sana, m.ism, m.telefon, m.oxirgi_sms
        from xizmat x left join mijoz m on m.raqam=x.raqam
        where x.id = (select max(id) from xizmat where raqam=x.raqam)
          and x.keyingi_sana <= ?
          and m.telefon is not null and m.telefon != ''
          and (m.oxirgi_sms is null or m.oxirgi_sms < ?)
        order by x.keyingi_sana
    """, (chegara, qayta))]


@app.get("/api/sms/royxat")
def sms_royxat(request: Request):
    ega(request)
    with db() as c:
        return sms_kerak(c)


@app.post("/api/sms/yubor")
def sms_yuborish(request: Request):
    ega(request)
    natija = []
    with db() as c:
        royxat = sms_kerak(c)
        for m in royxat:
            matn = sms.matn_tayyorla(m["ism"], m["keyingi_sana"], m["keyingi_km"])
            xabar, ok = sms.yubor(m["telefon"], matn)
            if ok:
                c.execute("update mijoz set oxirgi_sms=? where raqam=?",
                          (datetime.now().strftime("%Y-%m-%d"), m["raqam"]))
            natija.append({"raqam": m["raqam"], "natija": xabar, "ok": ok})
    return {"soni": len(natija), "yuborildi": sum(1 for n in natija if n["ok"]), "natija": natija}


class SmsBitta(BaseModel):
    raqam: str


@app.post("/api/sms/bitta")
def sms_bitta(b: SmsBitta, request: Request):
    ega(request)
    r = norm(b.raqam)
    with db() as c:
        m = c.execute("select * from mijoz where raqam=?", (r,)).fetchone()
        x = c.execute("select * from xizmat where raqam=? order by id desc limit 1", (r,)).fetchone()
        if not m or not x:
            raise HTTPException(404, "Mijoz topilmadi")
        matn = sms.matn_tayyorla(m["ism"], x["keyingi_sana"], x["keyingi_km"])
        xabar, ok = sms.yubor(m["telefon"], matn)
        if ok:
            c.execute("update mijoz set oxirgi_sms=? where raqam=?",
                      (datetime.now().strftime("%Y-%m-%d"), r))
    return {"natija": xabar, "ok": ok}
