import os, sqlite3, secrets, html
from datetime import datetime, timedelta
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from server import app, db, kim, ega, norm, hesh, sozlama_ol_c, PAPKA

import sms

with db() as c:
    c.executescript("""
    create table if not exists tovar(id integer primary key, nom text unique, birlik text, qoldiq real default 0, tannarx real default 0);
    create table if not exists sarf(id integer primary key, xizmat_id integer, tovar_id integer, miqdor real, tannarx_sum real);
    """)
    try:
        c.execute("alter table xizmat add column chek_tok text")
    except sqlite3.OperationalError:
        pass  # ustun allaqachon bor
    for row in c.execute("select id from xizmat where chek_tok is null"):
        c.execute("update xizmat set chek_tok=? where id=?", (secrets.token_urlsafe(8), row["id"]))


class Sarf(BaseModel):
    tovar_id: int
    miqdor: float

class Xizmat2(BaseModel):
    raqam: str
    rusum: str = ""
    ism: str = ""
    telefon: str = ""
    km: int
    moy: str = ""
    filtr: bool = False
    summa: int
    sarflar: list[Sarf] = []

class Tovar(BaseModel):
    nom: str
    birlik: str = "dona"

class Kirim(BaseModel):
    tovar_id: int
    miqdor: float
    narx: float

class Parol(BaseModel):
    eski: str
    yangi: str


@app.get("/ombor.js")
def ombor_js():
    return FileResponse(os.path.join(PAPKA, "ombor.js"), media_type="application/javascript")


@app.get("/api/tovar")
def tovar_royxat(request: Request):
    u = kim(request)
    with db() as c:
        rows = [dict(r) for r in c.execute("select * from tovar order by nom")]
    if u["rol"] != "ega":
        for r in rows:
            r.pop("tannarx", None)
    return rows


@app.post("/api/tovar")
def tovar_qosh(b: Tovar, request: Request):
    ega(request)
    nom = b.nom.strip()
    if len(nom) < 2:
        raise HTTPException(400, "Tovar nomi juda qisqa")
    with db() as c:
        try:
            c.execute("insert into tovar(nom,birlik) values(?,?)", (nom, b.birlik.strip() or "dona"))
        except sqlite3.IntegrityError:
            raise HTTPException(400, "Bunday tovar allaqachon bor")
    return {"ok": True}


@app.post("/api/kirim")
def kirim(b: Kirim, request: Request):
    ega(request)
    if b.miqdor <= 0 or b.narx < 0:
        raise HTTPException(400, "Miqdor va narxni to'g'ri kiriting")
    with db() as c:
        t = c.execute("select * from tovar where id=?", (b.tovar_id,)).fetchone()
        if not t:
            raise HTTPException(404, "Tovar topilmadi")
        yangi_q = t["qoldiq"] + b.miqdor
        tn = (max(t["qoldiq"], 0) * t["tannarx"] + b.miqdor * b.narx) / yangi_q
        c.execute("update tovar set qoldiq=?, tannarx=? where id=?", (yangi_q, tn, t["id"]))
    return {"ok": True}


class TovarTahrir(BaseModel):
    id: int
    nom: str
    birlik: str = "dona"
    qoldiq: float
    tannarx: float

class TovarId(BaseModel):
    id: int


@app.post("/api/tovar/tahrirla")
def tovar_tahrirla(b: TovarTahrir, request: Request):
    ega(request)
    nom = b.nom.strip()
    if len(nom) < 2:
        raise HTTPException(400, "Tovar nomi juda qisqa")
    if b.qoldiq < 0 or b.tannarx < 0:
        raise HTTPException(400, "Qoldiq va tannarxni to'g'ri kiriting")
    with db() as c:
        try:
            n = c.execute("update tovar set nom=?, birlik=?, qoldiq=?, tannarx=? where id=?",
                          (nom, b.birlik.strip() or "dona", b.qoldiq, b.tannarx, b.id)).rowcount
        except sqlite3.IntegrityError:
            raise HTTPException(400, "Bunday nomli tovar allaqachon bor")
    if not n:
        raise HTTPException(404, "Tovar topilmadi")
    return {"ok": True}


@app.post("/api/tovar/ochir")
def tovar_ochir(b: TovarId, request: Request):
    ega(request)
    with db() as c:
        n = c.execute("delete from tovar where id=?", (b.id,)).rowcount
    if not n:
        raise HTTPException(404, "Tovar topilmadi")
    return {"ok": True}


@app.post("/api/xizmat2")
def xizmat2(b: Xizmat2, request: Request):
    u = kim(request)
    r = norm(b.raqam)
    if len(r) < 5:
        raise HTTPException(400, "Mashina raqami juda qisqa")
    if b.km <= 0 or b.summa < 0:
        raise HTTPException(400, "Km va summani to'g'ri kiriting")
    now = datetime.now()
    with db() as c:
        s = sozlama_ol_c(c)
        c.execute("""insert into mijoz(raqam,rusum,ism,telefon) values(?,?,?,?)
                     on conflict(raqam) do update set rusum=excluded.rusum, ism=excluded.ism, telefon=excluded.telefon""",
                  (r, b.rusum.strip(), b.ism.strip(), b.telefon.strip()))
        nk = b.km + int(s["oraliq_km"])
        ns = (now + timedelta(days=int(s["oraliq_kun"]))).strftime("%Y-%m-%d")
        tok = secrets.token_urlsafe(8)
        cur = c.execute("insert into xizmat(raqam,sana,km,moy,filtr,summa,usta,keyingi_km,keyingi_sana,chek_tok) values(?,?,?,?,?,?,?,?,?,?)",
                        (r, now.isoformat(timespec="seconds"), b.km, b.moy.strip(), int(b.filtr), b.summa, u["login"], nk, ns, tok))
        xid = cur.lastrowid
        for sf in b.sarflar:
            if sf.miqdor <= 0:
                raise HTTPException(400, "Tovar miqdori noto'g'ri")
            t = c.execute("select * from tovar where id=?", (sf.tovar_id,)).fetchone()
            if not t:
                raise HTTPException(404, "Tovar topilmadi")
            if t["qoldiq"] < sf.miqdor:
                raise HTTPException(400, "Omborda %s yetarli emas (qoldiq: %s)" % (t["nom"], round(t["qoldiq"], 2)))
            c.execute("update tovar set qoldiq=qoldiq-? where id=?", (sf.miqdor, t["id"]))
            c.execute("insert into sarf(xizmat_id,tovar_id,miqdor,tannarx_sum) values(?,?,?,?)",
                      (xid, t["id"], sf.miqdor, sf.miqdor * t["tannarx"]))
    return {"id": xid, "keyingi_km": nk, "keyingi_sana": ns}


@app.get("/api/foyda")
def foyda_hisob(request: Request):
    ega(request)
    now = datetime.now()
    kun, oy = now.strftime("%Y-%m-%d"), now.strftime("%Y-%m-01")
    with db() as c:
        def f(p):
            t = c.execute("select coalesce(sum(summa),0) from xizmat where sana>=?", (p,)).fetchone()[0]
            x = c.execute("select coalesce(sum(s.tannarx_sum),0) from sarf s join xizmat z on z.id=s.xizmat_id where z.sana>=?", (p,)).fetchone()[0]
            return {"tushum": t, "xarajat": round(x), "foyda": round(t - x)}
        return {"bugun": f(kun), "oy": f(oy)}


@app.post("/api/parol")
def parol_almashtir(b: Parol, request: Request):
    u = kim(request)
    if len(b.yangi) < 6:
        raise HTTPException(400, "Yangi parol kamida 6 belgi bo'lsin")
    with db() as c:
        r = c.execute("select * from users where login=?", (u["login"],)).fetchone()
        if not secrets.compare_digest(r["hesh"], hesh(b.eski, r["tuz"])):
            raise HTTPException(400, "Eski parol noto'g'ri")
        tuz = secrets.token_hex(8)
        c.execute("update users set tuz=?, hesh=? where login=?", (tuz, hesh(b.yangi, tuz), u["login"]))
    return {"ok": True}


def _chek_sahifa(x, sarflar, servis):
    e = lambda s: html.escape(str(s or ""))
    jami = "{:,}".format(x["summa"]).replace(",", " ")
    sana = x["sana"][:16].replace("T", " ")
    filtr = ", filtr almashtirildi" if x["filtr"] else ""
    qismlar = ""
    if sarflar:
        qatorlar = "".join(f'<div class="r"><span>{e(r["nom"])}</span><span>{r["miqdor"]} {e(r["birlik"])}</span></div>' for r in sarflar)
        qismlar = f'<hr><p><b>Ishlatilgan ehtiyot qismlar:</b></p>{qatorlar}'
    return f"""<!doctype html><meta charset="utf-8"><title>Chek</title>
<style>body{{font:14px monospace;max-width:300px;margin:16px auto}}h3,p{{margin:4px 0}}hr{{border:0;border-top:1px dashed #000}}.r{{display:flex;justify-content:space-between}}</style>
<h3>{e(servis)}</h3><p>{e(sana)}</p><hr>
<p>Mashina: {e(x["raqam"])} {e(x["rusum"])}</p><p>Mijoz: {e(x["ism"])}</p><p>Km: {x["km"]}</p>
<p>Moy: {e(x["moy"])}{filtr}</p>{qismlar}<hr>
<div class="r"><b>Jami:</b><b>{jami} so'm</b></div><hr>
<p>Keyingi almashtirish: {x["keyingi_km"]} km yoki {e(x["keyingi_sana"])}</p><p>Rahmat!</p>
<script>print()</script>"""


@app.get("/chek/{xid}")
def chek(xid: int, request: Request):
    kim(request)
    with db() as c:
        x = c.execute("select x.*, m.ism, m.rusum from xizmat x left join mijoz m on m.raqam=x.raqam where x.id=?", (xid,)).fetchone()
        if not x:
            raise HTTPException(404, "Xizmat topilmadi")
        servis = sozlama_ol_c(c)["servis"]
        sarflar = c.execute("select t.nom, s.miqdor, t.birlik from sarf s join tovar t on t.id=s.tovar_id where s.xizmat_id=?",
                            (xid,)).fetchall()
    return HTMLResponse(_chek_sahifa(x, sarflar, servis))


@app.get("/chek/pub/{tok}")
def chek_pub(tok: str):
    """Mijoz SMS orqali olgan havola bilan (login talab qilinmaydi) chekni ko'radi."""
    with db() as c:
        x = c.execute("select x.*, m.ism, m.rusum from xizmat x left join mijoz m on m.raqam=x.raqam where x.chek_tok=?",
                      (tok,)).fetchone()
        if not x:
            raise HTTPException(404, "Chek topilmadi")
        servis = sozlama_ol_c(c)["servis"]
        sarflar = c.execute("select t.nom, s.miqdor, t.birlik from sarf s join tovar t on t.id=s.tovar_id where s.xizmat_id=?",
                            (x["id"],)).fetchall()
    return HTMLResponse(_chek_sahifa(x, sarflar, servis))


class SmsChek(BaseModel):
    xid: int


@app.post("/api/sms/chek")
def sms_chek_yubor(b: SmsChek, request: Request):
    kim(request)
    with db() as c:
        x = c.execute("""select x.chek_tok, x.summa, m.telefon, m.ism from xizmat x
                         left join mijoz m on m.raqam=x.raqam where x.id=?""", (b.xid,)).fetchone()
    if not x:
        raise HTTPException(404, "Xizmat topilmadi")
    if not x["telefon"]:
        raise HTTPException(400, "Bu mijozning telefon raqami yo'q")
    havola = f"{str(request.base_url).rstrip('/')}/chek/pub/{x['chek_tok']}"
    matn = (f"Hurmatli {x['ism'] or 'mijoz'}, xizmat bajarildi, jami {'{:,}'.format(x['summa']).replace(',', ' ')} so'm. "
            f"Chek: {havola}")
    xabar, ok = sms.yubor(x["telefon"], matn)
    return {"natija": xabar, "ok": ok}