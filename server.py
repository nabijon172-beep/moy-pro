import sqlite3, secrets, os, hashlib, csv, io
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

PAPKA = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(PAPKA, "moy_baza.db")
sessiyalar = {}
app = FastAPI()


def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def hesh(parol, tuz):
    return hashlib.pbkdf2_hmac("sha256", parol.encode(), tuz.encode(), 100000).hex()


def user_qosh(c, login, parol, rol):
    tuz = secrets.token_hex(8)
    c.execute("insert into users(login,tuz,hesh,rol) values(?,?,?,?)", (login, tuz, hesh(parol, tuz), rol))


with db() as c:
    c.executescript("""
    create table if not exists users(login text primary key, tuz text, hesh text, rol text);
    create table if not exists mijoz(raqam text primary key, rusum text, ism text, telefon text);
    create table if not exists xizmat(id integer primary key, raqam text, sana text, km integer, moy text, filtr integer, summa integer, usta text, keyingi_km integer, keyingi_sana text);
    create table if not exists sozlama(kalit text primary key, qiymat text);
    """)
    if not c.execute("select 1 from users").fetchone():
        user_qosh(c, "ega", os.environ.get("ADMIN_PAROL", "admin123"), "ega")
    for k, v in {"servis": "Moy servisi", "oraliq_km": "5000", "oraliq_kun": "180"}.items():
        c.execute("insert or ignore into sozlama values(?,?)", (k, v))


def sozlama_ol_c(c):
    return {r["kalit"]: r["qiymat"] for r in c.execute("select * from sozlama")}


def norm(r):
    return "".join(ch for ch in r.upper() if ch.isalnum())[:12]


def kim(request: Request):
    u = sessiyalar.get(request.cookies.get("moy_t"))
    if not u:
        raise HTTPException(401, "Kirish kerak")
    return u


def ega(request: Request):
    u = kim(request)
    if u["rol"] != "ega":
        raise HTTPException(403, "Bu bo'lim faqat egasi uchun")
    return u


class Login(BaseModel):
    login: str
    parol: str

class Xizmat(BaseModel):
    raqam: str
    rusum: str = ""
    ism: str = ""
    telefon: str = ""
    km: int
    moy: str = ""
    filtr: bool = False
    summa: int

class Sozlama(BaseModel):
    servis: str
    oraliq_km: int
    oraliq_kun: int

class Usta(BaseModel):
    login: str
    parol: str


@app.get("/")
def bosh():
    return FileResponse(os.path.join(PAPKA, "index.html"))


@app.post("/api/login")
def login(b: Login, resp: Response):
    with db() as c:
        u = c.execute("select * from users where login=?", (b.login.strip().lower(),)).fetchone()
    if not u or not secrets.compare_digest(u["hesh"], hesh(b.parol, u["tuz"])):
        raise HTTPException(401, "Login yoki parol noto'g'ri")
    t = secrets.token_urlsafe(24)
    sessiyalar[t] = {"login": u["login"], "rol": u["rol"]}
    resp.set_cookie("moy_t", t, httponly=True, samesite="lax", max_age=86400 * 30)
    return {"ok": True}


@app.post("/api/chiqish")
def chiqish(request: Request, resp: Response):
    sessiyalar.pop(request.cookies.get("moy_t"), None)
    resp.delete_cookie("moy_t")
    return {"ok": True}


@app.get("/api/holat")
def holat(request: Request):
    u = kim(request)
    now = datetime.now()
    bugun = now.strftime("%Y-%m-%d")
    chegara = (now + timedelta(days=14)).strftime("%Y-%m-%d")
    with db() as c:
        sn = c.execute("select count(*) n, coalesce(sum(summa),0) t from xizmat where sana like ?", (bugun + "%",)).fetchone()
        yaqin = [dict(r) for r in c.execute("""
            select x.raqam, x.keyingi_km, x.keyingi_sana, m.ism, m.telefon, m.rusum
            from xizmat x left join mijoz m on m.raqam=x.raqam
            where x.id = (select max(id) from xizmat where raqam=x.raqam) and x.keyingi_sana <= ?
            order by x.keyingi_sana""", (chegara,))]
        servis = sozlama_ol_c(c)["servis"]
    return {"rol": u["rol"], "servis": servis, "bugun": bugun, "bugun_soni": sn["n"], "yaqin": yaqin}


@app.get("/api/mijoz")
def mijoz_qidir(request: Request, q: str = ""):
    kim(request)
    q = "%" + q.upper().replace(" ", "") + "%"
    with db() as c:
        return [dict(r) for r in c.execute("""
            select m.*, (select max(sana) from xizmat where raqam=m.raqam) oxirgi,
                   (select count(*) from xizmat where raqam=m.raqam) soni
            from mijoz m where m.raqam like ? or upper(m.ism) like ? or m.telefon like ?
            order by oxirgi desc limit 50""", (q, q, q))]


@app.get("/api/mijoz/{raqam}")
def mijoz_tarix(raqam: str, request: Request):
    kim(request)
    r = norm(raqam)
    with db() as c:
        m = c.execute("select * from mijoz where raqam=?", (r,)).fetchone()
        if not m:
            raise HTTPException(404, "Mijoz topilmadi")
        tarix = [dict(x) for x in c.execute("select * from xizmat where raqam=? order by id desc", (r,))]
    return {"mijoz": dict(m), "tarix": tarix}


@app.post("/api/xizmat")
def xizmat_yoz(b: Xizmat, request: Request):
    u = kim(request)
    r = norm(b.raqam)
    if len(r) < 5:
        raise HTTPException(400, "Mashina raqami juda qisqa")
    if b.km <= 0 or b.summa < 0:
        raise HTTPException(400, "Km va summani to'g'ri kiriting")
    with db() as c:
        s = sozlama_ol_c(c)
        c.execute("""insert into mijoz(raqam,rusum,ism,telefon) values(?,?,?,?)
                     on conflict(raqam) do update set rusum=excluded.rusum, ism=excluded.ism, telefon=excluded.telefon""",
                  (r, b.rusum.strip(), b.ism.strip(), b.telefon.strip()))
        nk = b.km + int(s["oraliq_km"])
        ns = (datetime.now() + timedelta(days=int(s["oraliq_kun"]))).strftime("%Y-%m-%d")
        c.execute("insert into xizmat(raqam,sana,km,moy,filtr,summa,usta,keyingi_km,keyingi_sana) values(?,?,?,?,?,?,?,?,?)",
                  (r, datetime.now().isoformat(timespec="seconds"), b.km, b.moy.strip(), int(b.filtr), b.summa, u["login"], nk, ns))
    return {"keyingi_km": nk, "keyingi_sana": ns}


@app.get("/api/hisobot")
def hisobot(request: Request):
    ega(request)
    now = datetime.now()
    kun, oy = now.strftime("%Y-%m-%d"), now.strftime("%Y-%m-01")
    with db() as c:
        def yig(p):
            r = c.execute("select count(*) n, coalesce(sum(summa),0) t from xizmat where sana >= ?", (p,)).fetchone()
            return {"soni": r["n"], "tushum": r["t"]}
        ustalar = [dict(r) for r in c.execute(
            "select usta, count(*) soni, sum(summa) tushum from xizmat where sana >= ? group by usta order by tushum desc", (oy,))]
        return {"bugun": yig(kun), "oy": yig(oy), "ustalar": ustalar}


@app.get("/api/eksport")
def eksport(request: Request):
    ega(request)
    with db() as c:
        rows = c.execute("""select x.sana, x.raqam, m.rusum, m.ism, m.telefon, x.km, x.moy, x.filtr, x.summa, x.usta,
                            x.keyingi_km, x.keyingi_sana from xizmat x left join mijoz m on m.raqam=x.raqam order by x.id desc""").fetchall()
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(["Sana", "Raqam", "Rusum", "Ism", "Telefon", "Km", "Moy", "Filtr", "Summa", "Usta", "Keyingi km", "Keyingi sana"])
    for r in rows:
        w.writerow(list(r))
    return Response("\ufeff" + out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=moy_hisobot.csv"})


@app.get("/api/sozlama")
def sozlama_korish(request: Request):
    ega(request)
    with db() as c:
        return {"sozlama": sozlama_ol_c(c), "ustalar": [r["login"] for r in c.execute("select login from users where rol='usta'")]}


@app.post("/api/sozlama")
def sozlama_saqla(b: Sozlama, request: Request):
    ega(request)
    if b.oraliq_km < 500 or b.oraliq_kun < 7:
        raise HTTPException(400, "Oraliq juda kichik (kamida 500 km va 7 kun)")
    with db() as c:
        for k, v in {"servis": b.servis.strip() or "Moy servisi", "oraliq_km": b.oraliq_km, "oraliq_kun": b.oraliq_kun}.items():
            c.execute("insert or replace into sozlama values(?,?)", (k, str(v)))
    return {"ok": True}


@app.post("/api/usta")
def usta_qosh(b: Usta, request: Request):
    ega(request)
    l = b.login.strip().lower()
    if len(l) < 3 or len(b.parol) < 6:
        raise HTTPException(400, "Login kamida 3, parol kamida 6 belgi bo'lsin")
    with db() as c:
        if c.execute("select 1 from users where login=?", (l,)).fetchone():
            raise HTTPException(400, "Bunday login allaqachon bor")
        user_qosh(c, l, b.parol, "usta")
    return {"ok": True}
import ombor