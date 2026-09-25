import sqlite3, hashlib, secrets, sys
parol = sys.argv[1]
tuz = secrets.token_hex(8)
h = hashlib.pbkdf2_hmac("sha256", parol.encode(), tuz.encode(), 100000).hex()
c = sqlite3.connect("moy_baza.db")
c.execute("update users set tuz=?, hesh=? where login='ega'", (tuz, h))
c.commit()
print("Tayyor, parol yangilandi")