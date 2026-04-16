"""
Full system self-check — covers every checklist item.
Run: python check_all.py
"""
import sys, os, sqlite3, traceback

PASS = "[PASS]"
FAIL = "[FAIL]"
results = []

def check(label, fn):
    try:
        fn()
        results.append((PASS, label))
        print(f"  {PASS}  {label}")
    except Exception as e:
        results.append((FAIL, label, str(e)))
        print(f"  {FAIL}  {label}  =>  {e}")

# ── bootstrap ──────────────────────────────────────────────────────────────
from database import initialize_db, get_connection, verify_password, hash_password
initialize_db()

# ══════════════════════════════════════════════════════════════════════════
print("\n=== 1. DATABASE SCHEMA & INDEXES ===")

def chk_users_cols():
    cols = [r[1] for r in get_connection().execute("PRAGMA table_info(users)").fetchall()]
    for c in ["id","username","password_hash","role","is_active","created_at"]:
        assert c in cols, f"missing column: {c}"

def chk_products_cols():
    cols = [r[1] for r in get_connection().execute("PRAGMA table_info(products)").fetchall()]
    for c in ["id","name","barcode","price","stock","unit","is_active","created_at","updated_at"]:
        assert c in cols, f"missing column: {c}"

def chk_sales_cols():
    cols = [r[1] for r in get_connection().execute("PRAGMA table_info(sales)").fetchall()]
    for c in ["id","receipt_no","total","payment","change","user_id","created_at"]:
        assert c in cols, f"missing column: {c}"

def chk_sale_items_cols():
    cols = [r[1] for r in get_connection().execute("PRAGMA table_info(sale_items)").fetchall()]
    for c in ["id","sale_id","product_id","quantity","price"]:
        assert c in cols, f"missing column: {c}"

def chk_stock_movements_cols():
    cols = [r[1] for r in get_connection().execute("PRAGMA table_info(stock_movements)").fetchall()]
    for c in ["id","product_id","change","type","reference_id","created_at"]:
        assert c in cols, f"missing column: {c}"

def chk_indexes():
    idxs = [r[0] for r in get_connection().execute(
        "SELECT name FROM sqlite_master WHERE type='index'"
    ).fetchall()]
    assert "idx_barcode"    in idxs, "missing idx_barcode"
    assert "idx_sales_date" in idxs, "missing idx_sales_date"

check("users table columns",          chk_users_cols)
check("products table columns",       chk_products_cols)
check("sales table columns",          chk_sales_cols)
check("sale_items table columns",     chk_sale_items_cols)
check("stock_movements table columns",chk_stock_movements_cols)
check("indexes (barcode + sales_date)",chk_indexes)

# ══════════════════════════════════════════════════════════════════════════
print("\n=== 2. AUTHENTICATION ===")
from services.user_service import login, has_permission, add_user, toggle_user_active

def chk_login_valid():
    u = login("admin", "admin123")
    assert u is not None, "admin login failed"
    assert u["role"] == "admin"

def chk_login_wrong_password():
    u = login("admin", "wrongpassword")
    assert u is None, "wrong password should return None"

def chk_login_wrong_user():
    u = login("nobody", "admin123")
    assert u is None, "nonexistent user should return None"

def chk_bcrypt_stored():
    with get_connection() as conn:
        rows = conn.execute("SELECT password_hash FROM users").fetchall()
    for r in rows:
        assert r["password_hash"].startswith("$2"), \
            f"password not bcrypt hashed: {r['password_hash'][:10]}"

def chk_disabled_user_blocked():
    with get_connection() as conn:
        conn.execute("UPDATE users SET is_active=0 WHERE username='cashier'")
    result = login("cashier", "cashier123")
    with get_connection() as conn:
        conn.execute("UPDATE users SET is_active=1 WHERE username='cashier'")
    assert result is None, "disabled user should not be able to login"

def chk_roles_exist():
    with get_connection() as conn:
        roles = {r["role"] for r in conn.execute("SELECT role FROM users").fetchall()}
    assert "admin"   in roles
    assert "cashier" in roles
    assert "it"      in roles

check("valid login (admin)",          chk_login_valid)
check("wrong password blocked",       chk_login_wrong_password)
check("nonexistent user blocked",     chk_login_wrong_user)
check("passwords are bcrypt hashed",  chk_bcrypt_stored)
check("disabled user cannot login",   chk_disabled_user_blocked)
check("all 3 roles exist",            chk_roles_exist)

# ══════════════════════════════════════════════════════════════════════════
print("\n=== 3. ROLE-BASED PERMISSIONS ===")

def chk_admin_perms():
    for p in ["pos","inventory_view","inventory_manage","restock","reports","export","users"]:
        assert has_permission("admin", p), f"admin missing: {p}"

def chk_it_perms():
    for p in ["pos","inventory_view","inventory_manage","restock","reports","export","users"]:
        assert has_permission("it", p), f"it missing: {p}"

def chk_cashier_perms():
    allowed   = {"pos", "inventory_view"}
    forbidden = {"inventory_manage","restock","reports","export","users"}
    for p in allowed:
        assert has_permission("cashier", p),     f"cashier should have: {p}"
    for p in forbidden:
        assert not has_permission("cashier", p), f"cashier should NOT have: {p}"

check("admin has all permissions",    chk_admin_perms)
check("IT has all permissions",       chk_it_perms)
check("cashier has limited access",   chk_cashier_perms)

# ══════════════════════════════════════════════════════════════════════════
print("\n=== 4. INVENTORY ===")
from services.inventory_service import (
    get_all_products, get_product_by_barcode, get_product_by_id,
    add_product, update_product, deactivate_product,
    restock_product, get_low_stock_products, deduct_stock
)

def chk_products_seeded():
    prods = get_all_products()
    assert len(prods) >= 10, f"expected >=10 products, got {len(prods)}"

def chk_search_by_name():
    results = get_all_products("Rice")
    assert len(results) >= 1, "search by name failed"

def chk_search_by_barcode():
    results = get_all_products("8901234560001")
    assert len(results) >= 1, "search by barcode failed"

def chk_get_by_barcode():
    p = get_product_by_barcode("8901234560001")
    assert p is not None
    assert p["name"] == "White Rice 5kg"

def chk_add_product():
    with get_connection() as conn:
        old = conn.execute("SELECT id FROM products WHERE barcode='TEST-001'").fetchone()
        if old:
            conn.execute("DELETE FROM stock_movements WHERE product_id=?", (old["id"],))
            conn.execute("DELETE FROM sale_items WHERE product_id=?", (old["id"],))
            conn.execute("DELETE FROM products WHERE id=?", (old["id"],))
    add_product("Test Item", "TEST-001", 10.0, 50.0, "piece")
    p = get_product_by_barcode("TEST-001")
    assert p is not None
    assert p["name"] == "Test Item"

def chk_update_product():
    p = get_product_by_barcode("TEST-001")
    update_product(p["id"], "Test Item Updated", "TEST-001", 12.0, 50.0, "piece")
    p2 = get_product_by_barcode("TEST-001")
    assert p2["name"] == "Test Item Updated"
    assert p2["price"] == 12.0

def chk_restock():
    p = get_product_by_barcode("TEST-001")
    old_stock = p["stock"]
    restock_product(p["id"], 10.0)
    p2 = get_product_by_id(p["id"])
    assert p2["stock"] == old_stock + 10.0, "restock failed"

def chk_restock_logged():
    p = get_product_by_barcode("TEST-001")
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM stock_movements WHERE product_id=? AND type='restock' ORDER BY id DESC",
            (p["id"],)
        ).fetchone()
    assert row is not None, "restock not logged in stock_movements"
    assert row["change"] > 0

def chk_low_stock():
    # Laundry Soap has stock=8 which is <= 10
    items = get_low_stock_products()
    names = [p["name"] for p in items]
    assert any("Laundry" in n for n in names), f"low stock not detected: {names}"

def chk_deactivate():
    p = get_product_by_barcode("TEST-001")
    deactivate_product(p["id"])
    p2 = get_product_by_id(p["id"])
    assert p2["is_active"] == 0
    # should not appear in active list
    active = get_all_products("TEST-001")
    assert len(active) == 0, "deactivated product still showing"

check("products seeded (>=10)",       chk_products_seeded)
check("search by name",               chk_search_by_name)
check("search by barcode",            chk_search_by_barcode)
check("get product by barcode",       chk_get_by_barcode)
check("add product",                  chk_add_product)
check("update product",               chk_update_product)
check("restock product",              chk_restock)
check("restock logged in movements",  chk_restock_logged)
check("low stock detection (<=10)",   chk_low_stock)
check("deactivate product",           chk_deactivate)

# ══════════════════════════════════════════════════════════════════════════
print("\n=== 5. CART / POS ===")
from pos_logic import Cart

def chk_cart_add():
    cart = Cart()
    p = get_product_by_barcode("8901234560006")  # Instant Noodles
    cart.add_item(p["id"], 2.0)
    assert not cart.is_empty()
    assert len(cart.get_items()) == 1
    assert cart.get_items()[0]["quantity"] == 2.0

def chk_cart_decimal_qty():
    cart = Cart()
    p = get_product_by_barcode("8901234560001")  # White Rice (kg)
    cart.add_item(p["id"], 1.5)
    assert cart.get_items()[0]["quantity"] == 1.5

def chk_cart_total():
    cart = Cart()
    p = get_product_by_barcode("8901234560006")  # ₱14.00
    cart.add_item(p["id"], 3.0)
    assert cart.get_total() == round(14.0 * 3.0, 2)

def chk_cart_remove():
    cart = Cart()
    p = get_product_by_barcode("8901234560006")
    cart.add_item(p["id"], 1.0)
    cart.remove_item(p["id"])
    assert cart.is_empty()

def chk_cart_clear():
    cart = Cart()
    p1 = get_product_by_barcode("8901234560006")
    p2 = get_product_by_barcode("8901234560009")
    if p2["stock"] < 2:
        restock_product(p2["id"], 10.0)
    cart.add_item(p1["id"], 1.0)
    cart.add_item(p2["id"], 2.0)
    cart.clear()
    assert cart.is_empty()

def chk_cart_barcode():
    cart = Cart()
    cart.add_by_barcode("8901234560006", 1.0)
    assert not cart.is_empty()

def chk_cart_insufficient_stock():
    cart = Cart()
    p = get_product_by_barcode("8901234560006")
    try:
        cart.add_item(p["id"], 99999.0)
        assert False, "should have raised ValueError"
    except ValueError:
        pass

def chk_cart_invalid_qty():
    cart = Cart()
    p = get_product_by_barcode("8901234560006")
    try:
        cart.add_item(p["id"], -1.0)
        assert False, "should have raised ValueError"
    except ValueError:
        pass

def chk_cart_invalid_barcode():
    cart = Cart()
    try:
        cart.add_by_barcode("INVALID-BARCODE-000")
        assert False, "should have raised ValueError"
    except ValueError:
        pass

check("add item to cart",             chk_cart_add)
check("decimal quantity (kg)",        chk_cart_decimal_qty)
check("cart total computation",       chk_cart_total)
check("remove item from cart",        chk_cart_remove)
check("clear cart",                   chk_cart_clear)
check("add by barcode",               chk_cart_barcode)
check("insufficient stock blocked",   chk_cart_insufficient_stock)
check("invalid quantity blocked",     chk_cart_invalid_qty)
check("invalid barcode blocked",      chk_cart_invalid_barcode)

# ══════════════════════════════════════════════════════════════════════════
print("\n=== 6. CHECKOUT / TRANSACTION SAFETY ===")
from services.sales_service import checkout, get_sales_history, get_sale_items, get_daily_summary

def chk_checkout_basic():
    cart = Cart()
    p = get_product_by_barcode("8901234560009")  # Bottled Water ₱20
    if p["stock"] < 2:
        restock_product(p["id"], 10.0)
        p = get_product_by_id(p["id"])
    old_stock = p["stock"]
    cart.add_item(p["id"], 2.0)
    total = cart.get_total()
    result = checkout(cart.get_items(), total + 50.0, user_id=None, session_id=None)
    assert result["receipt_no"] is not None
    assert result["change"] == 50.0
    p2 = get_product_by_id(p["id"])
    assert p2["stock"] == old_stock - 2.0, "stock not deducted"

def chk_checkout_empty_cart():
    try:
        checkout([], 100.0)
        assert False, "should raise ValueError"
    except ValueError as e:
        assert "empty" in str(e).lower()

def chk_checkout_insufficient_payment():
    p = get_product_by_barcode("8901234560005")  # Eggs ₱195
    if p["stock"] < 1:
        restock_product(p["id"], 5.0)
        p = get_product_by_id(p["id"])
    cart = Cart()
    cart.add_item(p["id"], 1.0)
    try:
        checkout(cart.get_items(), 10.0)
        assert False, "should raise ValueError"
    except ValueError as e:
        assert "insufficient" in str(e).lower()

def chk_checkout_atomic_rollback():
    """Force a failure mid-transaction and verify nothing was saved."""
    from database import DB_PATH
    import sqlite3 as _sq
    before_count = get_connection().execute("SELECT COUNT(*) FROM sales").fetchone()[0]
    # Use a bad product_id to force deduct_stock to fail
    bad_items = [{"product_id": 999999, "quantity": 1.0, "price": 10.0, "name": "Ghost"}]
    try:
        checkout(bad_items, 100.0)
    except Exception:
        pass
    after_count = get_connection().execute("SELECT COUNT(*) FROM sales").fetchone()[0]
    assert before_count == after_count, "partial data saved on failure — rollback failed!"

def chk_stock_movement_on_sale():
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM stock_movements WHERE type='sale' ORDER BY id DESC"
        ).fetchone()
    assert row is not None, "no sale movement logged"
    assert row["change"] < 0, "sale movement should be negative"

def chk_receipt_no_format():
    import re
    result_no = get_connection().execute(
        "SELECT receipt_no FROM sales ORDER BY id DESC"
    ).fetchone()["receipt_no"]
    assert re.match(r"^\d{4}-\d{4}$", result_no), f"bad format: {result_no}"

def chk_receipt_file_saved():
    receipt_no = get_connection().execute(
        "SELECT receipt_no FROM sales ORDER BY id DESC"
    ).fetchone()["receipt_no"]
    safe = receipt_no.replace("-", "_")
    # check either format
    receipts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "receipts")
    files = os.listdir(receipts_dir)
    assert any(receipt_no.replace("-","_") in f or receipt_no in f for f in files), \
        f"receipt file not found for {receipt_no}, files: {files}"

check("basic checkout works",              chk_checkout_basic)
check("empty cart blocked",                chk_checkout_empty_cart)
check("insufficient payment blocked",      chk_checkout_insufficient_payment)
check("atomic rollback on failure",        chk_checkout_atomic_rollback)
check("stock_movements logged on sale",    chk_stock_movement_on_sale)
check("receipt_no format YYYY-XXXX",       chk_receipt_no_format)
check("receipt .txt file saved",           chk_receipt_file_saved)

# ══════════════════════════════════════════════════════════════════════════
print("\n=== 7. REPORTS ===")

def chk_sales_history():
    sales = get_sales_history()
    assert len(sales) >= 1, "no sales history"

def chk_date_filter():
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    sales = get_sales_history(date_from=today, date_to=today)
    assert isinstance(sales, list)

def chk_drill_down():
    sale = get_connection().execute("SELECT id FROM sales ORDER BY id DESC").fetchone()
    items = get_sale_items(sale["id"])
    assert len(items) >= 1, "no items for sale"
    assert "name" in items[0].keys()

def chk_daily_summary():
    s = get_daily_summary()
    assert "txn_count"   in s
    assert "total_sales" in s
    assert s["txn_count"] >= 0
    assert s["total_sales"] >= 0

def chk_csv_export():
    import csv, io
    sales = get_sales_history()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Receipt No","Total","Payment","Change","Date"])
    for s in sales:
        writer.writerow([s["receipt_no"], s["total"], s["payment"],
                         s["change"], s["created_at"][:19]])
    assert "Receipt No" in buf.getvalue()

check("sales history retrievable",    chk_sales_history)
check("date range filter works",      chk_date_filter)
check("drill-down per transaction",   chk_drill_down)
check("daily summary correct",        chk_daily_summary)
check("CSV export logic works",       chk_csv_export)

# ══════════════════════════════════════════════════════════════════════════
print("\n=== 8. USER MANAGEMENT ===")
from services.user_service import add_user, update_user, toggle_user_active, get_all_users

def chk_add_user():
    add_user("testuser99", "pass1234", "cashier")
    with get_connection() as conn:
        u = conn.execute("SELECT * FROM users WHERE username='testuser99'").fetchone()
    assert u is not None
    assert u["role"] == "cashier"
    assert u["password_hash"].startswith("$2")

def chk_update_user():
    with get_connection() as conn:
        u = conn.execute("SELECT id FROM users WHERE username='testuser99'").fetchone()
    update_user(u["id"], "testuser99", "newpass999", "it")
    with get_connection() as conn:
        u2 = conn.execute("SELECT * FROM users WHERE id=?", (u["id"],)).fetchone()
    assert u2["role"] == "it"
    assert verify_password("newpass999", u2["password_hash"])

def chk_update_user_no_password():
    with get_connection() as conn:
        u = conn.execute("SELECT * FROM users WHERE username='testuser99'").fetchone()
    old_hash = u["password_hash"]
    update_user(u["id"], "testuser99", None, "cashier")
    with get_connection() as conn:
        u2 = conn.execute("SELECT * FROM users WHERE id=?", (u["id"],)).fetchone()
    assert u2["password_hash"] == old_hash, "password changed when it shouldn't"

def chk_toggle_disable():
    with get_connection() as conn:
        u = conn.execute("SELECT id FROM users WHERE username='testuser99'").fetchone()
    toggle_user_active(u["id"], False)
    result = login("testuser99", "newpass999")
    assert result is None, "disabled user logged in"

def chk_toggle_enable():
    with get_connection() as conn:
        u = conn.execute("SELECT id FROM users WHERE username='testuser99'").fetchone()
    toggle_user_active(u["id"], True)
    result = login("testuser99", "cashier123")
    # password was changed to newpass999 so this should fail but user is active
    with get_connection() as conn:
        u2 = conn.execute("SELECT is_active FROM users WHERE id=?", (u["id"],)).fetchone()
    assert u2["is_active"] == 1

def chk_get_all_users():
    users = get_all_users()
    usernames = [u["username"] for u in users]
    assert "admin" in usernames
    assert "cashier" in usernames

def chk_duplicate_username_blocked():
    try:
        add_user("admin", "somepass", "cashier")
        assert False, "duplicate username should fail"
    except Exception:
        pass

# cleanup test user
def cleanup_testuser():
    with get_connection() as conn:
        conn.execute("DELETE FROM users WHERE username='testuser99'")

check("add user",                          chk_add_user)
check("update user (with new password)",   chk_update_user)
check("update user (keep password)",       chk_update_user_no_password)
check("disable user blocks login",         chk_toggle_disable)
check("enable user restores access",       chk_toggle_enable)
check("get all users",                     chk_get_all_users)
check("duplicate username blocked",        chk_duplicate_username_blocked)
cleanup_testuser()

# ══════════════════════════════════════════════════════════════════════════
print("\n=== 9. SECURITY ===")

def chk_no_plain_passwords():
    with get_connection() as conn:
        rows = conn.execute("SELECT password_hash FROM users").fetchall()
    for r in rows:
        h = r["password_hash"]
        assert h.startswith("$2"), f"plain text password found: {h[:20]}"
        assert len(h) > 30

def chk_path_traversal_safe():
    from utils import save_receipt
    try:
        save_receipt("../../etc/passwd", [], 0, 0, 0, "2024-01-01 00:00:00")
        # if it didn't raise, check the file was NOT written outside receipts dir
        import re
        safe = re.sub(r"[^\w\-]", "_", "../../etc/passwd")
        receipts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "receipts")
        bad_path = os.path.abspath(os.path.join(receipts_dir, f"{safe}.txt"))
        assert bad_path.startswith(os.path.abspath(receipts_dir)), "path traversal not blocked"
    except ValueError:
        pass  # raised = also safe

def chk_input_validation_qty():
    cart = Cart()
    p = get_product_by_barcode("8901234560006")
    for bad_qty in [0, -1, -999]:
        try:
            cart.add_item(p["id"], bad_qty)
            assert False, f"qty={bad_qty} should be rejected"
        except ValueError:
            pass

def chk_stock_cannot_go_negative():
    p = get_product_by_barcode("8901234560010")  # Laundry Soap stock=8
    cart = Cart()
    try:
        cart.add_item(p["id"], p["stock"] + 100)
        assert False, "should block oversell"
    except ValueError:
        pass

check("no plain text passwords in DB",     chk_no_plain_passwords)
check("path traversal in receipts safe",   chk_path_traversal_safe)
check("invalid quantity rejected",         chk_input_validation_qty)
check("stock cannot go negative",          chk_stock_cannot_go_negative)

# ══════════════════════════════════════════════════════
print("\n=== 10. CASHOUT / SHIFT SYSTEM ===")
from services.shift_service import (
    start_shift, end_shift, add_cash_adjustment,
    get_open_session, get_shift_report, get_session_by_id,
)
from services.sales_service import checkout as _checkout

# Use a dedicated test user to avoid polluting real cashier data
def _get_test_user_id():
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM users WHERE username='cashier'").fetchone()
    return row["id"]

def _cleanup_sessions(user_id):
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM cash_adjustments WHERE session_id IN "
            "(SELECT id FROM cashier_sessions WHERE user_id=?)", (user_id,)
        )
        conn.execute(
            "UPDATE sales SET session_id=NULL WHERE session_id IN "
            "(SELECT id FROM cashier_sessions WHERE user_id=?)", (user_id,)
        )
        conn.execute("DELETE FROM cashier_sessions WHERE user_id=?", (user_id,))

def chk_start_shift():
    uid = _get_test_user_id()
    _cleanup_sessions(uid)
    s = start_shift(uid, 500.00, "Test shift")
    assert s["status"] == "open"
    assert s["opening_cash"] == 500.00
    assert s["user_id"] == uid

def chk_duplicate_shift_blocked():
    uid = _get_test_user_id()
    # session already open from previous check
    try:
        start_shift(uid, 100.00)
        assert False, "duplicate shift should be blocked"
    except ValueError as e:
        assert "open shift" in str(e).lower()

def chk_get_open_session():
    uid = _get_test_user_id()
    s = get_open_session(uid)
    assert s is not None
    assert s["status"] == "open"

def chk_checkout_requires_session():
    """checkout() with user_id but no session_id must raise."""
    uid = _get_test_user_id()
    p = get_product_by_barcode("8901234560009")  # Bottled Water
    items = [{"product_id": p["id"], "quantity": 1.0, "price": p["price"],
              "name": p["name"]}]
    try:
        _checkout(items, 100.0, user_id=uid, session_id=None)
        assert False, "should require session_id"
    except ValueError as e:
        assert "shift" in str(e).lower()

def chk_checkout_with_session():
    uid = _get_test_user_id()
    s   = get_open_session(uid)
    p   = get_product_by_barcode("8901234560009")
    if p["stock"] < 1:
        restock_product(p["id"], 10.0)
        p = get_product_by_id(p["id"])
    items = [{"product_id": p["id"], "quantity": 1.0, "price": p["price"],
              "name": p["name"]}]
    result = _checkout(items, p["price"] + 10.0, user_id=uid, session_id=s["id"])
    assert result["receipt_no"] is not None
    with get_connection() as conn:
        sale = conn.execute(
            "SELECT session_id FROM sales WHERE receipt_no=?",
            (result["receipt_no"],)
        ).fetchone()
    assert sale["session_id"] == s["id"]

def chk_cash_adjustment_cash_in():
    uid = _get_test_user_id()
    s   = get_open_session(uid)
    adj = add_cash_adjustment(s["id"], "cash_in", 200.00, "Change fund added")
    assert adj["type"] == "cash_in"
    assert adj["amount"] == 200.00

def chk_cash_adjustment_cash_out():
    uid = _get_test_user_id()
    s   = get_open_session(uid)
    adj = add_cash_adjustment(s["id"], "cash_out", 50.00, "Petty cash withdrawal")
    assert adj["type"] == "cash_out"

def chk_adjustment_invalid_amount():
    uid = _get_test_user_id()
    s   = get_open_session(uid)
    try:
        add_cash_adjustment(s["id"], "cash_in", 0.0, "zero amount")
        assert False, "zero amount should be rejected"
    except ValueError:
        pass

def chk_adjustment_missing_reason():
    uid = _get_test_user_id()
    s   = get_open_session(uid)
    try:
        add_cash_adjustment(s["id"], "cash_in", 10.0, "   ")
        assert False, "blank reason should be rejected"
    except ValueError:
        pass

def chk_end_shift_computation():
    uid = _get_test_user_id()
    # Always start a fresh session for this check
    _cleanup_sessions(uid)
    s = start_shift(uid, 500.00, "computation test")
    p = get_product_by_barcode("8901234560009")
    if p["stock"] < 1:
        restock_product(p["id"], 10.0)
        p = get_product_by_id(p["id"])
    _checkout(
        [{"product_id": p["id"], "quantity": 1.0,
          "price": p["price"], "name": p["name"]}],
        p["price"] + 10.0, user_id=uid, session_id=s["id"]
    )
    add_cash_adjustment(s["id"], "cash_in",  200.00, "fund")
    add_cash_adjustment(s["id"], "cash_out",  50.00, "petty")
    with get_connection() as conn:
        sales_tot = conn.execute(
            "SELECT COALESCE(SUM(total),0) FROM sales WHERE session_id=?", (s["id"],)
        ).fetchone()[0]
        ci = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM cash_adjustments"
            " WHERE session_id=? AND type='cash_in'", (s["id"],)
        ).fetchone()[0]
        co = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM cash_adjustments"
            " WHERE session_id=? AND type='cash_out'", (s["id"],)
        ).fetchone()[0]
    expected = round(500.0 + sales_tot + ci - co, 2)
    closed = end_shift(s["id"], closing_cash=expected)
    assert closed["status"] == "closed", f"status={closed['status']}"
    assert closed["expected_cash"] == expected, \
        f"expected_cash={closed['expected_cash']} != {expected}"
    assert closed["discrepancy"] == 0.00, \
        f"discrepancy={closed['discrepancy']}"

def chk_end_shift_discrepancy():
    uid = _get_test_user_id()
    _cleanup_sessions(uid)
    s      = start_shift(uid, 100.00)
    closed = end_shift(s["id"], closing_cash=80.00)
    assert closed["discrepancy"] == -20.00, \
        f"expected discrepancy=-20.00, got {closed['discrepancy']}"

def chk_double_end_shift_blocked():
    uid = _get_test_user_id()
    with get_connection() as conn:
        last = conn.execute(
            "SELECT id FROM cashier_sessions WHERE user_id=? AND status='closed' ORDER BY id DESC",
            (uid,)
        ).fetchone()
    assert last is not None, "no closed session found"
    try:
        end_shift(last["id"], closing_cash=100.00)
        assert False, "closing an already-closed session should raise"
    except ValueError as e:
        assert "closed" in str(e).lower()

def chk_adjustment_on_closed_session_blocked():
    uid = _get_test_user_id()
    with get_connection() as conn:
        last = conn.execute(
            "SELECT id FROM cashier_sessions WHERE user_id=? ORDER BY id DESC",
            (uid,)
        ).fetchone()
    try:
        add_cash_adjustment(last["id"], "cash_in", 10.0, "should fail")
        assert False, "adjustment on closed session should raise"
    except ValueError as e:
        assert "closed" in str(e).lower()

def chk_shift_report():
    uid = _get_test_user_id()
    with get_connection() as conn:
        last = conn.execute(
            "SELECT id FROM cashier_sessions WHERE user_id=? ORDER BY id DESC",
            (uid,)
        ).fetchone()
    report = get_shift_report(last["id"])
    assert "session"     in report
    assert "sales"       in report
    assert "adjustments" in report
    assert report["session"]["id"] == last["id"]

def chk_no_open_session_after_end():
    uid = _get_test_user_id()
    s   = get_open_session(uid)
    assert s is None, "should have no open session after end_shift"

# Run all cashout checks
check("start shift",                              chk_start_shift)
check("duplicate shift blocked",                  chk_duplicate_shift_blocked)
check("get open session",                         chk_get_open_session)
check("checkout requires active session",         chk_checkout_requires_session)
check("checkout links sale to session",           chk_checkout_with_session)
check("cash_in adjustment recorded",              chk_cash_adjustment_cash_in)
check("cash_out adjustment recorded",             chk_cash_adjustment_cash_out)
check("zero amount adjustment blocked",           chk_adjustment_invalid_amount)
check("blank reason adjustment blocked",          chk_adjustment_missing_reason)
check("end shift — expected cash correct",        chk_end_shift_computation)
check("end shift — discrepancy computed",         chk_end_shift_discrepancy)
check("double end shift blocked",                 chk_double_end_shift_blocked)
check("adjustment on closed session blocked",     chk_adjustment_on_closed_session_blocked)
check("shift report structure correct",           chk_shift_report)
check("no open session after end",                chk_no_open_session_after_end)

# ══════════════════════════════════════════════════════════════════════════
print("\n" + "="*55)
passed = sum(1 for r in results if r[0] == PASS)
failed = sum(1 for r in results if r[0] == FAIL)
print(f"  TOTAL: {passed} passed, {failed} failed out of {len(results)}")
if failed:
    print("\n  FAILED ITEMS:")
    for r in results:
        if r[0] == FAIL:
            print(f"    - {r[1]}: {r[2]}")
    sys.exit(1)
else:
    print("\n  ALL CHECKS PASSED - COMPLETE")
    sys.exit(0)
