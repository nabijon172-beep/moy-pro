import os
import sqlite3
from datetime import datetime
from typing import Literal

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from server import PAPKA, app, db, ega


with db() as c:
    c.executescript("""
    create table if not exists shop_products (
        id integer primary key,
        name text not null,
        category text not null,
        description text not null default '',
        image_url text not null default '',
        price integer not null check(price >= 0),
        stock integer not null default 0 check(stock >= 0),
        active integer not null default 1
    );
    create table if not exists shop_orders (
        id integer primary key,
        customer_name text not null,
        phone text not null,
        fulfillment text not null,
        address text not null default '',
        comment text not null default '',
        total integer not null,
        status text not null default 'Yangi',
        created_at text not null
    );
    create table if not exists shop_order_items (
        id integer primary key,
        order_id integer not null references shop_orders(id),
        product_id integer,
        product_name text not null,
        price integer not null,
        quantity integer not null
    );
    """)


class ProductInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    category: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=1000)
    image_url: str = Field(default="", max_length=500)
    price: int = Field(ge=0)
    stock: int = Field(ge=0)
    active: bool = True


class CartItem(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=50)


class OrderInput(BaseModel):
    customer_name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=7, max_length=30)
    fulfillment: Literal["delivery", "pickup"]
    address: str = Field(default="", max_length=500)
    comment: str = Field(default="", max_length=500)
    items: list[CartItem] = Field(min_length=1, max_length=50)


class OrderStatus(BaseModel):
    status: Literal["Yangi", "Qabul qilindi", "Tayyorlanmoqda", "Yo'lda", "Bajarildi", "Bekor qilindi"]


@app.get("/magazin")
def shop_page():
    return FileResponse(os.path.join(PAPKA, "magazin.html"))


@app.get("/api/shop/products")
def shop_products(q: str = "", category: str = ""):
    with db() as c:
        rows = c.execute("""
            select id, name, category, description, image_url, price, stock
            from shop_products where active=1 and stock>0
              and (?='' or name like ? or category like ?)
              and (?='' or category=?)
            order by category, name limit 200
        """, (q, f"%{q}%", f"%{q}%", category, category)).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/shop/orders")
def shop_create_order(body: OrderInput, request: Request):
    name = body.customer_name.strip()
    phone = "".join(ch for ch in body.phone if ch.isdigit() or ch == "+")
    address = body.address.strip()
    if len(name) < 2 or len(phone) < 7:
        raise HTTPException(400, "Ism va telefon raqamini tekshiring")
    if body.fulfillment == "delivery" and len(address) < 5:
        raise HTTPException(400, "Dastavka uchun manzilni kiriting")

    quantities = {}
    for item in body.items:
        quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity
    with db() as c:
        products = {}
        for pid, qty in quantities.items():
            product = c.execute("select * from shop_products where id=? and active=1", (pid,)).fetchone()
            if not product:
                raise HTTPException(400, "Mahsulot topilmadi yoki sotuvda yo'q")
            if product["stock"] < qty:
                raise HTTPException(400, f"{product['name']} dan yetarli qoldiq yo'q")
            products[pid] = (product, qty)
        total = sum(product["price"] * qty for product, qty in products.values())
        cur = c.execute("""insert into shop_orders
            (customer_name,phone,fulfillment,address,comment,total,status,created_at)
            values(?,?,?,?,?,?,?,?)""",
            (name, phone, body.fulfillment, address, body.comment.strip(), total,
             "Yangi", datetime.now().isoformat(timespec="seconds")))
        order_id = cur.lastrowid
        for product, qty in products.values():
            c.execute("update shop_products set stock=stock-? where id=?", (qty, product["id"]))
            c.execute("""insert into shop_order_items
                (order_id,product_id,product_name,price,quantity) values(?,?,?,?,?)""",
                (order_id, product["id"], product["name"], product["price"], qty))
    return {"ok": True, "order_id": order_id, "total": total}


@app.get("/api/shop/admin/products")
def shop_admin_products(request: Request):
    ega(request)
    with db() as c:
        return [dict(row) for row in c.execute("select * from shop_products order by id desc")]


@app.post("/api/shop/admin/products")
def shop_add_product(body: ProductInput, request: Request):
    ega(request)
    with db() as c:
        cur = c.execute("""insert into shop_products
            (name,category,description,image_url,price,stock,active) values(?,?,?,?,?,?,?)""",
            (body.name.strip(), body.category.strip(), body.description.strip(), body.image_url.strip(),
             body.price, body.stock, int(body.active)))
    return {"ok": True, "id": cur.lastrowid}


@app.put("/api/shop/admin/products/{product_id}")
def shop_update_product(product_id: int, body: ProductInput, request: Request):
    ega(request)
    with db() as c:
        result = c.execute("""update shop_products set name=?,category=?,description=?,image_url=?,
            price=?,stock=?,active=? where id=?""",
            (body.name.strip(), body.category.strip(), body.description.strip(), body.image_url.strip(),
             body.price, body.stock, int(body.active), product_id))
    if not result.rowcount:
        raise HTTPException(404, "Mahsulot topilmadi")
    return {"ok": True}


@app.get("/api/shop/admin/orders")
def shop_admin_orders(request: Request):
    ega(request)
    with db() as c:
        orders = [dict(row) for row in c.execute("select * from shop_orders order by id desc limit 200")]
        for order in orders:
            order["items"] = [dict(item) for item in c.execute(
                "select product_name,price,quantity from shop_order_items where order_id=?", (order["id"],))]
    return orders


@app.patch("/api/shop/admin/orders/{order_id}")
def shop_update_order(order_id: int, body: OrderStatus, request: Request):
    ega(request)
    with db() as c:
        row = c.execute("select status from shop_orders where id=?", (order_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Buyurtma topilmadi")
        if row["status"] == "Bekor qilindi" and body.status != "Bekor qilindi":
            raise HTTPException(400, "Bekor qilingan buyurtmani qayta ochib bo'lmaydi")
        if body.status == "Bekor qilindi" and row["status"] != "Bekor qilindi":
            for item in c.execute("select product_id,quantity from shop_order_items where order_id=?", (order_id,)):
                if item["product_id"] is not None:
                    c.execute("update shop_products set stock=stock+? where id=?", (item["quantity"], item["product_id"]))
        c.execute("update shop_orders set status=? where id=?", (body.status, order_id))
    return {"ok": True}


# Importing this module registers the storefront and admin API routes.
