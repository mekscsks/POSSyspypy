import os
import re
from datetime import datetime
from database import get_connection

RECEIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "receipts")


def generate_receipt_no() -> str:
    year = datetime.now().strftime("%Y")
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM sales WHERE receipt_no LIKE ?", (f"{year}-%",)
        ).fetchone()
        seq = (row[0] or 0) + 1
    return f"{year}-{seq:04d}"


def format_currency(amount: float) -> str:
    return f"₱{amount:,.2f}"


def _safe_filename(name: str) -> str:
    """Strip any characters that could cause path traversal."""
    return re.sub(r"[^\w\-]", "_", name)


def save_receipt(
    receipt_no: str,
    items: list,
    total: float,
    payment: float,
    change: float,
    timestamp: str,
) -> str:
    os.makedirs(RECEIPTS_DIR, exist_ok=True)
    safe_name = _safe_filename(receipt_no)
    path = os.path.join(RECEIPTS_DIR, f"{safe_name}.txt")

    # Ensure path stays inside RECEIPTS_DIR
    if not os.path.abspath(path).startswith(os.path.abspath(RECEIPTS_DIR)):
        raise ValueError("Invalid receipt path.")

    W = 42
    lines = [
        "=" * W,
        "GROCERY STORE POS SYSTEM".center(W),
        f"Receipt No: {receipt_no}".center(W),
        timestamp.center(W),
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
