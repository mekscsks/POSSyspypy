from datetime import datetime
from database import get_connection

LOW_STOCK_THRESHOLD = 10


def get_all_products(search=""):
    with get_connection() as conn:
        if search:
            like = f"%{search}%"
            return conn.execute(
                "SELECT * FROM products WHERE is_active=1 AND (name LIKE ? OR barcode LIKE ?) ORDER BY name",
                (like, like),
            ).fetchall()
        return conn.execute(
            "SELECT * FROM products WHERE is_active=1 ORDER BY name"
        ).fetchall()


def get_product_by_barcode(barcode):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM products WHERE barcode=? AND is_active=1", (barcode,)
        ).fetchone()


def get_product_by_id(product_id):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM products WHERE id=?", (product_id,)
        ).fetchone()


def add_product(name, barcode, price, stock, unit):
    now = datetime.now().isoformat()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO products(name,barcode,price,stock,unit,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (name, barcode, float(price), float(stock), unit, now, now),
        )


def update_product(product_id, name, barcode, price, stock, unit):
    now = datetime.now().isoformat()
    with get_connection() as conn:
        conn.execute(
            "UPDATE products SET name=?,barcode=?,price=?,stock=?,unit=?,updated_at=? WHERE id=?",
            (name, barcode, float(price), float(stock), unit, now, product_id),
        )


def deactivate_product(product_id):
    now = datetime.now().isoformat()
    with get_connection() as conn:
        conn.execute(
            "UPDATE products SET is_active=0,updated_at=? WHERE id=?", (now, product_id)
        )


def restock_product(product_id, qty):
    now = datetime.now().isoformat()
    with get_connection() as conn:
        conn.execute(
            "UPDATE products SET stock=stock+?,updated_at=? WHERE id=?",
            (float(qty), now, product_id),
        )
        conn.execute(
            "INSERT INTO stock_movements(product_id,change,type,created_at) VALUES(?,?,'restock',?)",
            (product_id, float(qty), now),
        )


def deduct_stock(product_id, qty, sale_id, conn):
    now = datetime.now().isoformat()
    row = conn.execute(
        "SELECT stock FROM products WHERE id=?", (product_id,)
    ).fetchone()
    if row is None or row["stock"] < qty:
        raise ValueError(f"Insufficient stock for product id={product_id}")
    conn.execute(
        "UPDATE products SET stock=stock-?,updated_at=? WHERE id=?",
        (float(qty), now, product_id),
    )
    conn.execute(
        "INSERT INTO stock_movements(product_id,change,type,reference_id,created_at) VALUES(?,?,'sale',?,?)",
        (product_id, -float(qty), sale_id, now),
    )


def get_low_stock_products():
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM products WHERE is_active=1 AND stock <= ? ORDER BY stock",
            (LOW_STOCK_THRESHOLD,),
        ).fetchall()


def adjust_stock(product_id, new_stock):
    now = datetime.now().isoformat()
    with get_connection() as conn:
        old = conn.execute(
            "SELECT stock FROM products WHERE id=?", (product_id,)
        ).fetchone()
        if old is None:
            raise ValueError("Product not found")
        diff = float(new_stock) - old["stock"]
        conn.execute(
            "UPDATE products SET stock=?,updated_at=? WHERE id=?",
            (float(new_stock), now, product_id),
        )
        conn.execute(
            "INSERT INTO stock_movements(product_id,change,type,created_at) VALUES(?,?,'adjustment',?)",
            (product_id, diff, now),
        )
