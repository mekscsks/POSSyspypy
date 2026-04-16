from datetime import datetime
from database import get_connection


# ── Queries ────────────────────────────────────────────────────────────────────

def get_open_session(user_id: int) -> dict | None:
    """Return the single open session for this user, or None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM cashier_sessions WHERE user_id=? AND status='open'",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def get_session_by_id(session_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM cashier_sessions WHERE id=?", (session_id,)
        ).fetchone()
    return dict(row) if row else None


# ── Start Shift ────────────────────────────────────────────────────────────────

def start_shift(user_id: int, opening_cash: float, notes: str = "") -> dict:
    """
    Open a new cashier session.
    Raises ValueError if:
      - opening_cash < 0
      - user already has an open session (duplicate shift prevention)
    """
    if opening_cash < 0:
        raise ValueError("Opening cash cannot be negative.")

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM cashier_sessions WHERE user_id=? AND status='open'",
            (user_id,),
        ).fetchone()
        if existing:
            raise ValueError(
                f"You already have an open shift (Session #{existing['id']}). "
                "End your current shift before starting a new one."
            )
        now = datetime.now().isoformat()
        cur = conn.execute(
            "INSERT INTO cashier_sessions(user_id, opening_cash, status, opened_at, notes)"
            " VALUES(?,?, 'open', ?,?)",
            (user_id, opening_cash, now, notes),
        )
        session_id = cur.lastrowid
    return get_session_by_id(session_id)


# ── Cash Adjustment ────────────────────────────────────────────────────────────

def add_cash_adjustment(session_id: int, adj_type: str, amount: float, reason: str) -> dict:
    """
    Record a cash_in or cash_out adjustment against an open session.
    Raises ValueError for invalid input or closed/missing session.
    """
    if adj_type not in ("cash_in", "cash_out"):
        raise ValueError("Type must be 'cash_in' or 'cash_out'.")
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")
    if not reason.strip():
        raise ValueError("Reason is required.")

    with get_connection() as conn:
        session = conn.execute(
            "SELECT id, status FROM cashier_sessions WHERE id=?", (session_id,)
        ).fetchone()
        if not session:
            raise ValueError("Session not found.")
        if session["status"] != "open":
            raise ValueError("Cannot adjust a closed session.")

        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO cash_adjustments(session_id, type, amount, reason, created_at)"
            " VALUES(?,?,?,?,?)",
            (session_id, adj_type, amount, reason.strip(), now),
        )
        adj_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        return dict(conn.execute(
            "SELECT * FROM cash_adjustments WHERE id=?", (adj_id,)
        ).fetchone())


# ── End Shift ──────────────────────────────────────────────────────────────────

def end_shift(session_id: int, closing_cash: float, notes: str = "") -> dict:
    """
    Close a session and compute expected_cash / discrepancy.

    expected_cash = opening_cash
                  + SUM(sales.total linked to this session)
                  + SUM(cash_in adjustments)
                  - SUM(cash_out adjustments)

    The sales.total column already represents net cash collected per transaction
    (payment - change = total), keeping the formula clean and ready for future
    multi-payment-method support (just filter by payment_method='cash' later).

    Raises ValueError for:
      - closing_cash < 0
      - session not found or already closed
    """
    if closing_cash < 0:
        raise ValueError("Closing cash cannot be negative.")

    with get_connection() as conn:
        session = conn.execute(
            "SELECT * FROM cashier_sessions WHERE id=?", (session_id,)
        ).fetchone()
        if not session:
            raise ValueError("Session not found.")
        if session["status"] != "open":
            raise ValueError("This shift is already closed.")

        # Sum of all sales totals in this session
        sales_total = conn.execute(
            "SELECT COALESCE(SUM(total), 0) FROM sales WHERE session_id=?",
            (session_id,),
        ).fetchone()[0]

        # Cash adjustments
        cash_in = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM cash_adjustments"
            " WHERE session_id=? AND type='cash_in'",
            (session_id,),
        ).fetchone()[0]
        cash_out = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM cash_adjustments"
            " WHERE session_id=? AND type='cash_out'",
            (session_id,),
        ).fetchone()[0]

        expected_cash = round(session["opening_cash"] + sales_total + cash_in - cash_out, 2)
        discrepancy   = round(closing_cash - expected_cash, 2)
        now           = datetime.now().isoformat()

        conn.execute(
            """UPDATE cashier_sessions
               SET status='closed', closing_cash=?, expected_cash=?,
                   discrepancy=?, closed_at=?, notes=?
               WHERE id=?""",
            (closing_cash, expected_cash, discrepancy, now, notes or session["notes"], session_id),
        )
        # Return the updated row within the same connection before it closes
        updated = conn.execute(
            "SELECT * FROM cashier_sessions WHERE id=?", (session_id,)
        ).fetchone()
        return dict(updated)


# ── Report ─────────────────────────────────────────────────────────────────────

def get_shift_report(session_id: int) -> dict:
    """
    Return a complete shift report dict including session info,
    all sales, and all cash adjustments.
    """
    with get_connection() as conn:
        session = conn.execute(
            "SELECT cs.*, u.username FROM cashier_sessions cs"
            " JOIN users u ON u.id = cs.user_id WHERE cs.id=?",
            (session_id,),
        ).fetchone()
        if not session:
            raise ValueError("Session not found.")

        sales = conn.execute(
            "SELECT receipt_no, total, payment, change, created_at"
            " FROM sales WHERE session_id=? ORDER BY created_at",
            (session_id,),
        ).fetchall()

        adjustments = conn.execute(
            "SELECT type, amount, reason, created_at FROM cash_adjustments"
            " WHERE session_id=? ORDER BY created_at",
            (session_id,),
        ).fetchall()

    return {
        "session":     dict(session),
        "sales":       [dict(s) for s in sales],
        "adjustments": [dict(a) for a in adjustments],
    }


# ── Crash Recovery ─────────────────────────────────────────────────────────────

def recover_stale_sessions(max_hours: int = 24) -> list[int]:
    """
    Find sessions that have been open longer than max_hours with no sales activity.
    Returns list of stale session IDs for admin review — does NOT auto-close them.
    Admins should call end_shift() manually after reviewing.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT cs.id FROM cashier_sessions cs
               WHERE cs.status = 'open'
               AND (
                   julianday('now') - julianday(cs.opened_at)
               ) * 24 > ?
               AND NOT EXISTS (
                   SELECT 1 FROM sales s
                   WHERE s.session_id = cs.id
                   AND (julianday('now') - julianday(s.created_at)) * 24 < ?
               )""",
            (max_hours, max_hours),
        ).fetchall()
    return [r["id"] for r in rows]


def get_all_open_sessions() -> list[dict]:
    """Admin view: all currently open sessions across all cashiers."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT cs.*, u.username FROM cashier_sessions cs"
            " JOIN users u ON u.id = cs.user_id WHERE cs.status='open'"
            " ORDER BY cs.opened_at",
        ).fetchall()
    return [dict(r) for r in rows]


def get_sessions_by_user(user_id: int, limit: int = 20) -> list[dict]:
    """History of sessions for a given user."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM cashier_sessions WHERE user_id=?"
            " ORDER BY opened_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]
