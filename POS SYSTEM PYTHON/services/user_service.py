from datetime import datetime
from database import get_connection, hash_password, verify_password


def login(username: str, password: str):
    """Returns user dict if credentials valid and active, else None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username=? AND is_active=1", (username,)
        ).fetchone()
    if row and verify_password(password, row["password_hash"]):
        return dict(row)
    return None


def get_all_users():
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, username, role, is_active, created_at FROM users ORDER BY role, username"
        ).fetchall()


def add_user(username: str, password: str, role: str):
    if not username or not password:
        raise ValueError("Username and password are required.")
    now = datetime.now().isoformat()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO users(username,password_hash,role,created_at) VALUES(?,?,?,?)",
            (username.strip(), hash_password(password), role, now),
        )


def update_user(user_id: int, username: str, password: str | None, role: str):
    if not username:
        raise ValueError("Username is required.")
    with get_connection() as conn:
        if password:
            conn.execute(
                "UPDATE users SET username=?,password_hash=?,role=? WHERE id=?",
                (username.strip(), hash_password(password), role, user_id),
            )
        else:
            conn.execute(
                "UPDATE users SET username=?,role=? WHERE id=?",
                (username.strip(), role, user_id),
            )


def toggle_user_active(user_id: int, is_active: bool):
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET is_active=? WHERE id=?",
            (1 if is_active else 0, user_id),
        )


# ── Permissions ────────────────────────────────────────────────────────────────

PERMISSIONS: dict[str, set[str]] = {
    "admin":   {"pos", "inventory_view", "inventory_manage", "restock", "reports", "export", "users"},
    "it":      {"pos", "inventory_view", "inventory_manage", "restock", "reports", "export", "users"},
    "cashier": {"pos", "inventory_view"},
}


def has_permission(role: str, permission: str) -> bool:
    return permission in PERMISSIONS.get(role, set())
