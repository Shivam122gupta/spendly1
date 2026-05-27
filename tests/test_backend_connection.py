"""tests/test_backend_connection.py

Unit and route tests for Step 5 — backend connection for the profile page.

Covers:
  - get_user_by_id
  - get_summary_stats
  - get_recent_transactions
  - get_category_breakdown
  - GET /profile route (unauthenticated + authenticated)

Each test runs against a fresh in-memory SQLite DB (see conftest.py).
"""

import pytest
from werkzeug.security import generate_password_hash

import database.db as db_module
from database.queries import (
    get_user_by_id,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
)


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

_counter = 0

def _unique_email(prefix="user"):
    """Return a unique email so no test collides on the UNIQUE constraint."""
    global _counter
    _counter += 1
    return f"{prefix}{_counter}@spendly.test"


def _insert_user(name="Test User"):
    email = _unique_email(name.lower().replace(" ", ""))
    conn = db_module.get_db()
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (name, email, generate_password_hash("password123")),
    )
    uid = cursor.lastrowid
    conn.commit()
    conn.close()
    return uid, email


def _insert_expenses(uid, expenses):
    """Insert a list of (amount, category, date, description) tuples."""
    conn = db_module.get_db()
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description)"
        " VALUES (?, ?, ?, ?, ?)",
        [(uid, a, c, d, desc) for (a, c, d, desc) in expenses],
    )
    conn.commit()
    conn.close()


SAMPLE_EXPENSES = [
    (100.00, "Bills",     "2026-04-01", "Electric bill"),
    ( 50.00, "Food",      "2026-04-05", "Groceries"),
    ( 25.00, "Transport", "2026-04-10", "Bus pass"),
]


# ------------------------------------------------------------------ #
# App / client fixtures                                                #
# ------------------------------------------------------------------ #

@pytest.fixture()
def app_instance():
    import app as flask_app
    flask_app.app.config.update(TESTING=True, SECRET_KEY="test-secret")
    return flask_app.app


@pytest.fixture()
def client(app_instance):
    return app_instance.test_client()


# ------------------------------------------------------------------ #
# get_user_by_id                                                       #
# ------------------------------------------------------------------ #

class TestGetUserById:
    def test_valid_id_returns_dict(self):
        uid, email = _insert_user("Alice")
        result = get_user_by_id(uid)
        assert result is not None
        assert result["name"]  == "Alice"
        assert result["email"] == email
        parts = result["member_since"].split(" ")
        assert len(parts) == 2          # "Month YYYY"
        assert parts[1].isdigit()

    def test_nonexistent_id_returns_none(self):
        assert get_user_by_id(99999999) is None


# ------------------------------------------------------------------ #
# get_summary_stats                                                    #
# ------------------------------------------------------------------ #

class TestGetSummaryStats:
    def test_with_expenses(self):
        uid, _ = _insert_user()
        _insert_expenses(uid, SAMPLE_EXPENSES)
        result = get_summary_stats(uid)
        assert result["total_spent"]       == pytest.approx(175.00)
        assert result["transaction_count"] == 3
        assert result["top_category"]      == "Bills"

    def test_no_expenses_returns_zeros(self):
        uid, _ = _insert_user()
        result  = get_summary_stats(uid)
        assert result["total_spent"]       == 0.0
        assert result["transaction_count"] == 0
        assert result["top_category"]      == "—"


# ------------------------------------------------------------------ #
# get_recent_transactions                                              #
# ------------------------------------------------------------------ #

class TestGetRecentTransactions:
    def test_with_expenses_newest_first(self):
        uid, _ = _insert_user()
        _insert_expenses(uid, SAMPLE_EXPENSES)
        rows = get_recent_transactions(uid)
        assert len(rows) == 3
        dates = [r["date"] for r in rows]
        assert dates == sorted(dates, reverse=True)

    def test_all_keys_present(self):
        uid, _ = _insert_user()
        _insert_expenses(uid, SAMPLE_EXPENSES)
        rows = get_recent_transactions(uid)
        for r in rows:
            assert set(r.keys()) >= {"date", "description", "category", "amount"}
            assert isinstance(r["amount"], float)
            assert isinstance(r["description"], str)

    def test_null_description_becomes_empty_string(self):
        uid, _ = _insert_user()
        _insert_expenses(uid, [(10.00, "Food", "2026-01-01", None)])
        rows = get_recent_transactions(uid)
        assert rows[0]["description"] == ""

    def test_no_expenses_returns_empty_list(self):
        uid, _ = _insert_user()
        assert get_recent_transactions(uid) == []

    def test_limit_respected(self):
        uid, _ = _insert_user()
        _insert_expenses(uid, SAMPLE_EXPENSES)
        assert len(get_recent_transactions(uid, limit=2)) == 2


# ------------------------------------------------------------------ #
# get_category_breakdown                                               #
# ------------------------------------------------------------------ #

class TestGetCategoryBreakdown:
    def test_ordered_by_amount_desc(self):
        uid, _ = _insert_user()
        _insert_expenses(uid, SAMPLE_EXPENSES)
        result = get_category_breakdown(uid)
        assert len(result) == 3
        assert result[0]["name"] == "Bills"
        amounts = [c["amount"] for c in result]
        assert amounts == sorted(amounts, reverse=True)

    def test_pct_sums_to_100(self):
        uid, _ = _insert_user()
        _insert_expenses(uid, SAMPLE_EXPENSES)
        result = get_category_breakdown(uid)
        assert sum(c["pct"] for c in result) == 100

    def test_pct_values_are_integers(self):
        uid, _ = _insert_user()
        _insert_expenses(uid, SAMPLE_EXPENSES)
        for c in get_category_breakdown(uid):
            assert isinstance(c["pct"], int)

    def test_no_expenses_returns_empty_list(self):
        uid, _ = _insert_user()
        assert get_category_breakdown(uid) == []


# ------------------------------------------------------------------ #
# GET /profile route                                                   #
# ------------------------------------------------------------------ #

class TestProfileRoute:
    def test_unauthenticated_redirects_to_login(self, client):
        resp = client.get("/profile")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_authenticated_returns_200(self, client, app_instance):
        from unittest.mock import patch as mpatch
        uid, email = _insert_user("Demo User")
        _insert_expenses(uid, SAMPLE_EXPENSES)

        # Patch the names as imported into app.py so the route uses our test DB
        with mpatch("app.get_user_by_id",        side_effect=get_user_by_id), \
             mpatch("app.get_summary_stats",      side_effect=get_summary_stats), \
             mpatch("app.get_recent_transactions",side_effect=get_recent_transactions), \
             mpatch("app.get_category_breakdown", side_effect=get_category_breakdown):

            with client.session_transaction() as sess:
                sess["user_id"]   = uid
                sess["user_name"] = "Demo User"

            resp = client.get("/profile")

        assert resp.status_code == 200
        body = resp.data.decode()

        assert "Demo User"    in body
        assert "Arjun Sharma" not in body
        assert "₹"            in body
        assert "Bills"        in body   # top category

    def test_stale_session_clears_and_redirects(self, client, app_instance):
        """Session with non-existent user_id should redirect to login."""
        from unittest.mock import patch as mpatch
        with mpatch("app.get_user_by_id", side_effect=get_user_by_id):
            with client.session_transaction() as sess:
                sess["user_id"]   = 99999999
                sess["user_name"] = "Ghost"

            resp = client.get("/profile")

        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]
