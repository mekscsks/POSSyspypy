import sqlite3
from datetime import datetime
from database import DB_PATH, get_connection
from services.inventory_service import deduct_stock
from utils import generate_receipt_no, save_receipt


def checkout(cart_items: list, payment: float, user_id: int | None = None,
             session_id: int | None = None) -> dict:
    """
    Atomic checkout: BEGIN → validate session → insert sale → insert items
                     → deduct stock → log movements → COMMIT. ROLLBACK on failure.
    Requires an active cashier session when user_id is provided.
    """
    if not cart_items:
        raise ValueError("Cart is empty.")

    # Enforce active session for all cashier transactions
    if user_id is not None and session_id is None:
        raise ValueError(
            "No active shift. Please open a shift before processing transactions."
        )

    total = round(sum(i["quantity"] * i["price"] for i in cart_items), 2)
    if payment < total:
        raise ValueError(f"Insufficient payment. Total is ₱{total:,.2f}")

    change     = round(payment - total, 2)
    receipt_no = generate_receipt_no()
    now        = datetime.now().isoformat()
    timestamp  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("BEGIN")

        # Re-validate session is still open inside the transaction
        if session_id is not None:
            sess = conn.execute(
                "SELECT status FROM cashier_sessions WHERE id=?", (session_id,)
            ).fetchone()
            if not sess or sess["status"] != "open":
                raise ValueError("Shift has been closed. Cannot process transaction.")

        conn.execute(
            "INSERT INTO sales(receipt_no,total,payment,change,user_id,session_id,created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (receipt_no, total, payment, change, user_id, session_id, now),
        )
        sale_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        for item in cart_items:
            deduct_stock(item["product_id"], item["quantity"], sale_id, conn)
            conn.execute(
                "INSERT INTO sale_items(sale_id,product_id,quantity,price) VALUES(?,?,?,?)",
                (sale_id, item["product_id"], item["quantity"], item["price"]),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    receipt_items = [
        (i["name"], i["quantity"], i["price"], round(i["quantity"] * i["price"], 2))
        for i in cart_items
    ]
    receipt_path = save_receipt(receipt_no, receipt_items, total, payment, change, timestamp)
    return {
        "receipt_no":   receipt_no,
        "total":        total,
        "payment":      payment,
        "change":       change,
        "receipt_path": receipt_path,
        "timestamp":    timestamp,
    }


def get_sales_history(date_from: str | None = None, date_to: str | None = None) -> list:
    with get_connection() as conn:
        query, params, conditions = "SELECT * FROM sales", [], []
        if date_from:
            conditions.append("created_at >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("created_at <= ?")
            params.append(date_to + "T23:59:59")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC"
        return conn.execute(query, params).fetchall()


def get_sale_items(sale_id: int) -> list:
    with get_connection() as conn:
        return conn.execute(
            "SELECT si.*, p.name, p.unit FROM sale_items si"
            " JOIN products p ON p.id=si.product_id WHERE si.sale_id=?",
            (sale_id,),
        ).fetchall()


def get_daily_summary(date: str | None = None) -> dict:
    target = date or datetime.now().strftime("%Y-%m-%d")
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as txn_count, COALESCE(SUM(total),0) as total_sales"
            " FROM sales WHERE created_at LIKE ?",
            (f"{target}%",),
        ).fetchone()
        return dict(row)
