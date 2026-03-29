from datetime import datetime
from database import get_connection


def login(username, password):
    """Returns user row if credentials valid and active, else None."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE username=? AND password=? AND is_active=1",
            (username, password),
        ).fetchone()


def get_all_users():
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM users ORDER BY role, username"
        ).fetchall()


def add_user(username, password, role):
    now = datetime.now().isoformat()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO users(username,password,role,created_at) VALUES(?,?,?,?)",
            (username, password, role, now),
        )


def update_user(user_id, username, password, role):
    with get_connection() as conn:
        if password:
            conn.execute(
                "UPDATE users SET username=?,password=?,role=? WHERE id=?",
                (username, password, role, user_id),
            )
        else:
            conn.execute(
                "UPDATE users SET username=?,role=? WHERE id=?",
                (username, role, user_id),
            )


def toggle_user_active(user_id, is_active):
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET is_active=? WHERE id=?",
            (1 if is_active else 0, user_id),
        )


# Role permission map
PERMISSIONS = {
    "admin":   {"pos", "inventory_view", "inventory_manage", "restock", "reports", "export", "users"},
    "it":      {"pos", "inventory_view", "inventory_manage", "restock", "reports", "export", "users"},
    "cashier": {"pos", "inventory_view"},
}


def has_permission(role, permission):
    return permission in PERMISSIONS.get(role, set())
