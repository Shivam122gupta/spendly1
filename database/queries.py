"""database/queries.py

Pure SQLite query helpers for the Spendly profile page.
No Flask imports — only stdlib and database.db.get_db().

Sections (filled in by three parallel subagents):
  1. Transaction history  — get_recent_transactions()
  2. Summary stats        — get_user_by_id(), get_summary_stats()
  3. Category breakdown   — get_category_breakdown()
"""

from datetime import datetime

from database.db import get_db


def _date_filter(date_from, date_to):
    """Return (clause, params) for an optional inclusive date BETWEEN filter.

    When both ISO date strings are provided returns a non-empty SQL clause
    and the two bound values as a list.  Otherwise returns ('', []) so
    callers can always do  ``sql + clause``  and  ``[uid] + params``
    without any branching.
    """
    if date_from and date_to:
        return "AND date BETWEEN ? AND ? ", [date_from, date_to]
    return "", []


# ------------------------------------------------------------------ #
# Section 1 — Transaction history                                     #
# ------------------------------------------------------------------ #

def get_recent_transactions(user_id, limit=10, date_from=None, date_to=None):
    """Return the *limit* most recent expenses for *user_id*, newest-first.

    Each element is a plain dict with keys:
        date        (str)  "YYYY-MM-DD"
        description (str)  empty string if NULL
        category    (str)
        amount      (float)

    When *date_from* and *date_to* are both provided (ISO strings), only
    expenses within that inclusive range are returned.
    Returns an empty list if the user has no expenses.
    """
    conn = get_db()
    try:
        date_clause, date_params = _date_filter(date_from, date_to)
        cursor = conn.execute(
            "SELECT date, description, category, amount "
            "FROM expenses "
            "WHERE user_id = ? "
            + date_clause +
            "ORDER BY date DESC "
            "LIMIT ?",
            [user_id] + date_params + [limit],
        )
        rows = cursor.fetchall()
        return [
            {
                "date": row["date"],
                "description": row["description"] if row["description"] is not None else "",
                "category": row["category"],
                "amount": float(row["amount"]),
            }
            for row in rows
        ]
    finally:
        conn.close()


# ------------------------------------------------------------------ #
# Section 2 — Summary stats                                           #
# ------------------------------------------------------------------ #

def get_user_by_id(user_id):
    """Return a dict {name, email, member_since} for *user_id*, or None.

    member_since is formatted as "Month YYYY" (e.g. "May 2026").
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT name, email, created_at FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
        if row is None:
            return None
        member_since = datetime.strptime(row["created_at"][:10], "%Y-%m-%d").strftime("%B %Y")
        return {
            "name": row["name"],
            "email": row["email"],
            "member_since": member_since,
        }
    finally:
        conn.close()


def get_summary_stats(user_id, date_from=None, date_to=None):
    """Return a dict {total_spent, transaction_count, top_category}.

    total_spent      (float) — 0.0 if no expenses
    transaction_count (int)  — 0 if no expenses
    top_category     (str)   — "—" if no expenses

    When *date_from* and *date_to* are both provided (ISO strings), only
    expenses within that inclusive range are counted.
    """
    conn = get_db()
    try:
        date_clause, date_params = _date_filter(date_from, date_to)

        # ── Total spent and transaction count ─────────────────────────
        row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS cnt "
            "FROM expenses WHERE user_id = ? " + date_clause,
            [user_id] + date_params,
        ).fetchone()
        total_spent       = float(row["total"])
        transaction_count = int(row["cnt"])

        # ── Top category ──────────────────────────────────────────────
        top_row = conn.execute(
            "SELECT category FROM expenses "
            "WHERE user_id = ? " + date_clause +
            "GROUP BY category "
            "ORDER BY SUM(amount) DESC "
            "LIMIT 1",
            [user_id] + date_params,
        ).fetchone()
        top_category = top_row["category"] if top_row else "—"

        return {
            "total_spent":        total_spent,
            "transaction_count":  transaction_count,
            "top_category":       top_category,
        }
    finally:
        conn.close()


# ------------------------------------------------------------------ #
# Section 3 — Category breakdown                                      #
# ------------------------------------------------------------------ #

def get_category_breakdown(user_id, date_from=None, date_to=None):
    """Return a list of dicts ordered by amount desc.

    Each element has:
        name   (str)
        amount (float)
        pct    (int)  — integer percentage of grand total

    pct values must sum to exactly 100 (largest category absorbs remainder).
    Returns an empty list if the user has no expenses.

    When *date_from* and *date_to* are both provided (ISO strings), only
    expenses within that inclusive range are included.
    """
    db = get_db()
    try:
        date_clause, date_params = _date_filter(date_from, date_to)

        cursor = db.execute(
            "SELECT category, SUM(amount) AS total "
            "FROM expenses "
            "WHERE user_id = ? " + date_clause +
            "GROUP BY category "
            "ORDER BY total DESC",
            [user_id] + date_params,
        )
        rows = cursor.fetchall()
        if not rows:
            return []
        grand = sum(r["total"] for r in rows)
        result = [
            {
                "name": r["category"],
                "amount": r["total"],
                "pct": round(r["total"] / grand * 100),
            }
            for r in rows
        ]
        diff = 100 - sum(c["pct"] for c in result)
        result[0]["pct"] += diff
        return result
    finally:
        db.close()
