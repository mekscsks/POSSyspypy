import os
from datetime import datetime
from database import get_connection

RECEIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "receipts")


def generate_receipt_no():
    year = datetime.now().strftime("%Y")
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM sales WHERE receipt_no LIKE ?", (f"{year}-%",)
        ).fetchone()
        seq = (row[0] or 0) + 1
    return f"{year}-{seq:04d}"


def format_currency(amount):
    return f"₱{amount:,.2f}"


def save_receipt(receipt_no, items, total, payment, change, timestamp):
    os.makedirs(RECEIPTS_DIR, exist_ok=True)
    path = os.path.join(RECEIPTS_DIR, f"{receipt_no}.txt")
    W = 42
    lines = [
        "=" * W,
        "GROCERY STORE POS SYSTEM".center(W),
        f"Receipt No: {receipt_no}".center(W),
        f"{timestamp}".center(W),
        "=" * W,
        f"{'ITEM':<20}{'QTY':>5}{'PRICE':>8}{'AMT':>9}",
        "-" * W,
    ]
    for name, qty, price, subtotal in items:
        q = f"{qty:.3f}".rstrip("0").rstrip(".")
        lines.append(f"{name[:20]:<20}{q:>5}{price:>8.2f}{subtotal:>9.2f}")
    lines += [
        "-" * W,
        f"{'TOTAL:':<30}{total:>12.2f}",
        f"{'CASH:':<30}{payment:>12.2f}",
        f"{'CHANGE:':<30}{change:>12.2f}",
        "=" * W,
        "Thank you for shopping!".center(W),
        "=" * W,
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path
