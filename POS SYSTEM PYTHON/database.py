import sqlite3
import os
import bcrypt
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pos.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def initialize_db():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role          TEXT NOT NULL DEFAULT 'cashier'
                              CHECK(role IN ('admin','cashier','it')),
                is_active     INTEGER NOT NULL DEFAULT 1,
                created_at    TEXT NOT NULL
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

            CREATE TABLE IF NOT EXISTS cashier_sessions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL REFERENCES users(id),
                opening_cash  REAL    NOT NULL CHECK(opening_cash >= 0),
                closing_cash  REAL,
                expected_cash REAL,
                discrepancy   REAL,
                status        TEXT    NOT NULL DEFAULT 'open'
                              CHECK(status IN ('open','closed')),
                opened_at     TEXT    NOT NULL,
                closed_at     TEXT,
                notes         TEXT
            );

            CREATE TABLE IF NOT EXISTS cash_adjustments (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL REFERENCES cashier_sessions(id),
                type       TEXT    NOT NULL CHECK(type IN ('cash_in','cash_out')),
                amount     REAL    NOT NULL CHECK(amount > 0),
                reason     TEXT    NOT NULL,
                created_at TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_session_user   ON cashier_sessions(user_id, status);
            CREATE INDEX IF NOT EXISTS idx_session_status ON cashier_sessions(status);
        """)
        _migrate_users(conn)
        _migrate_sales_session(conn)
        _seed(conn)


def _migrate_users(conn):
    """Rename 'password' column to 'password_hash' if old schema exists."""
    # Clean up any leftover migration table first
    conn.execute("DROP TABLE IF EXISTS users_old")
    cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "password" not in cols or "password_hash" in cols:
        return  # already migrated or fresh DB
    rows = conn.execute("SELECT id, username, password, role, is_active, created_at FROM users").fetchall()
    now = datetime.now().isoformat()
    conn.execute("ALTER TABLE users RENAME TO users_old")
    conn.execute("""
        CREATE TABLE users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL DEFAULT 'cashier'
                          CHECK(role IN ('admin','cashier','it')),
            is_active     INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL
        )
    """)
    for row in rows:
        old_pw   = row["password"]
        new_hash = old_pw if old_pw.startswith("$2") else hash_password(old_pw)
        conn.execute(
            "INSERT INTO users(id,username,password_hash,role,is_active,created_at) VALUES(?,?,?,?,?,?)",
            (row["id"], row["username"], new_hash, row["role"],
             row["is_active"], row["created_at"] or now),
        )
    conn.execute("DROP TABLE users_old")


def _migrate_sales_session(conn):
    """Add session_id column to sales if it doesn't exist yet."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(sales)").fetchall()]
    if "session_id" not in cols:
        conn.execute("ALTER TABLE sales ADD COLUMN session_id INTEGER REFERENCES cashier_sessions(id)")


def _seed(conn):
    now = datetime.now().isoformat()
    default_users = [
        ("admin",   "admin123",   "admin"),
        ("cashier", "cashier123", "cashier"),
        ("it",      "it123",      "it"),
    ]
    for username, plain, role in default_users:
        exists = conn.execute(
            "SELECT id FROM users WHERE username=?", (username,)
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO users(username,password_hash,role,created_at) VALUES(?,?,?,?)",
                (username, hash_password(plain), role, now),
            )

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
