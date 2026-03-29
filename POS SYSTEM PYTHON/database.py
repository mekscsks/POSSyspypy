import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pos.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def initialize_db():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                username   TEXT UNIQUE NOT NULL,
                password   TEXT NOT NULL,
                role       TEXT NOT NULL DEFAULT 'cashier'
                           CHECK(role IN ('admin','cashier','it')),
                is_active  INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS products (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                barcode    TEXT UNIQUE NOT NULL,
                price      REAL NOT NULL CHECK(price > 0),
                stock      REAL NOT NULL DEFAULT 0 CHECK(stock >= 0),
                unit       TEXT NOT NULL DEFAULT 'piece' CHECK(unit IN ('piece','kg')),
                is_active  INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sales (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                receipt_no TEXT UNIQUE NOT NULL,
                total      REAL NOT NULL,
                payment    REAL NOT NULL,
                change     REAL NOT NULL,
                user_id    INTEGER REFERENCES users(id),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sale_items (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id    INTEGER NOT NULL REFERENCES sales(id),
                product_id INTEGER NOT NULL REFERENCES products(id),
                quantity   REAL NOT NULL,
                price      REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS stock_movements (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id   INTEGER NOT NULL REFERENCES products(id),
                change       REAL NOT NULL,
                type         TEXT NOT NULL CHECK(type IN ('sale','restock','adjustment')),
                reference_id INTEGER,
                created_at   TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_barcode    ON products(barcode);
            CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(created_at);
        """)
        _seed(conn)


def _seed(conn):
    now = datetime.now().isoformat()

    # seed default users
    default_users = [
        ("admin",   "admin123",   "admin"),
        ("cashier", "cashier123", "cashier"),
        ("it",      "it123",      "it"),
    ]
    for username, password, role in default_users:
        conn.execute(
            "INSERT OR IGNORE INTO users(username,password,role,created_at) VALUES(?,?,?,?)",
            (username, password, role, now),
        )

    # seed products only once
    if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]:
        return
    products = [
        ("White Rice 5kg",   "8901234560001", 285.00, 100.0, "kg"),
        ("Cooking Oil 1L",   "8901234560002",  95.00,  50.0, "piece"),
        ("Sugar 1kg",        "8901234560003",  68.00,  80.0, "kg"),
        ("Salt 250g",        "8901234560004",  18.00, 120.0, "piece"),
        ("Eggs Tray/30",     "8901234560005", 195.00,  30.0, "piece"),
        ("Instant Noodles",  "8901234560006",  14.00, 200.0, "piece"),
        ("Canned Sardines",  "8901234560007",  32.00, 150.0, "piece"),
        ("Bread Loaf",       "8901234560008",  65.00,  40.0, "piece"),
        ("Bottled Water 1L", "8901234560009",  20.00, 100.0, "piece"),
        ("Laundry Soap",     "8901234560010",  28.00,   8.0, "piece"),
    ]
    conn.executemany(
        "INSERT INTO products(name,barcode,price,stock,unit,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
        [(n, b, p, s, u, now, now) for n, b, p, s, u in products],
    )
