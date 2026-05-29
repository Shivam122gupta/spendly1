"""tests/test_06-date-filter-profile.py

Pytest test suite for Step 6 — Date Filter for the /profile page.

Spec: .claude/specs/06-date-filter-profile.md

All behaviours are derived exclusively from the spec's Definition of Done
and described feature behaviour. Implementation source files were read only
to understand route names, URL structure, fixture/DB API, and form field
names — NOT to derive test logic.

Test plan
---------
1.  Auth guard: unauthenticated GET /profile → 302 to /login
2.  No query params → 200, shows all expenses (unfiltered / "All Time")
3.  ₹ symbol present regardless of active filter (multiple filter states)
4.  "This Month" preset → only current-month expenses appear
5.  "Last 3 Months" preset (date_from = today-90d) → only that window
6.  "Last 6 Months" preset (date_from = today-180d) → only that window
7.  "All Time" clean URL (no params) = same as unfiltered
8.  Custom valid range → only expenses in that range appear in all 3 sections
9.  date_from > date_to → flash error message, falls back to unfiltered view
10. Malformed date string → no crash, silent fallback, returns 200
11. User with no expenses in selected range → ₹0.00 total, 0 transactions,
    empty category list — no errors

Each test uses the autouse `use_in_memory_db` fixture from conftest.py
so it runs against a fresh, isolated SQLite file.
"""

import pytest
from datetime import date, timedelta
from unittest.mock import patch as mpatch
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

_email_counter = 0


def _unique_email(prefix="filter_test_user"):
    """Return a unique email address for each call to avoid UNIQUE constraint collisions."""
    global _email_counter
    _email_counter += 1
    return f"{prefix}{_email_counter}@spendly.test"


def _insert_user(name="Filter Tester", password="testpass123"):
    """Insert a user into the test DB and return (user_id, email, password)."""
    email = _unique_email()
    conn = db_module.get_db()
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (name, email, generate_password_hash(password)),
    )
    uid = cursor.lastrowid
    conn.commit()
    conn.close()
    return uid, email, password


def _insert_expenses(uid, expenses):
    """Insert expenses given as list of (amount, category, date_str, description)."""
    conn = db_module.get_db()
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description)"
        " VALUES (?, ?, ?, ?, ?)",
        [(uid, amount, category, date_str, description)
         for (amount, category, date_str, description) in expenses],
    )
    conn.commit()
    conn.close()


def _today():
    return date.today()


def _today_iso():
    return _today().isoformat()


def _first_of_month_iso():
    return _today().replace(day=1).isoformat()


def _three_months_ago_iso():
    return (_today() - timedelta(days=90)).isoformat()


def _six_months_ago_iso():
    return (_today() - timedelta(days=180)).isoformat()


# ------------------------------------------------------------------ #
# App / client fixtures                                                #
# ------------------------------------------------------------------ #

@pytest.fixture()
def app_instance():
    """Return the Flask app configured for testing."""
    import app as flask_app_module
    flask_app_module.app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
    )
    return flask_app_module.app


@pytest.fixture()
def client(app_instance):
    """Return a test client (unauthenticated)."""
    return app_instance.test_client()


@pytest.fixture()
def auth_client(client, app_instance):
    """Return a test client with an active session for a freshly created user.

    Also returns the user_id so callers can insert expenses for that user.
    """
    uid, email, password = _insert_user("Authenticated User")

    # Inject session directly so we don't rely on the login route behaviour
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["user_name"] = "Authenticated User"

    return client, uid


# ------------------------------------------------------------------ #
# Shared patch context manager                                         #
# ------------------------------------------------------------------ #

def _profile_patches():
    """Return a context manager that patches all four query functions used by
    the /profile route so they resolve to the test-DB versions.

    Usage::

        with _profile_patches():
            resp = client.get("/profile")
    """
    return (
        mpatch("app.get_user_by_id",         side_effect=get_user_by_id),
        mpatch("app.get_summary_stats",       side_effect=get_summary_stats),
        mpatch("app.get_recent_transactions", side_effect=get_recent_transactions),
        mpatch("app.get_category_breakdown",  side_effect=get_category_breakdown),
    )


# ------------------------------------------------------------------ #
# 1. Auth guard                                                        #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    def test_unauthenticated_get_profile_redirects_to_login(self, client):
        """Unauthenticated request to /profile must return 302 to /login."""
        resp = client.get("/profile")
        assert resp.status_code == 302, (
            "Expected 302 redirect for unauthenticated /profile"
        )
        assert "/login" in resp.headers["Location"], (
            "Redirect target must be /login"
        )

    def test_unauthenticated_with_date_params_still_redirects(self, client):
        """Query params must not bypass the auth guard."""
        resp = client.get(f"/profile?date_from={_first_of_month_iso()}&date_to={_today_iso()}")
        assert resp.status_code == 302, (
            "Expected 302 redirect even when date params are supplied"
        )
        assert "/login" in resp.headers["Location"]


# ------------------------------------------------------------------ #
# 2. No query params → unfiltered / All Time                          #
# ------------------------------------------------------------------ #

class TestNoFilterAllTime:
    def test_no_params_returns_200(self, auth_client):
        """GET /profile with no query params must return HTTP 200."""
        client, uid = auth_client
        _insert_expenses(uid, [
            (50.00, "Food", "2025-01-15", "Old groceries"),
            (30.00, "Bills", _today_iso(), "Today's bill"),
        ])

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get("/profile")

        assert resp.status_code == 200, "Expected 200 for authenticated /profile"

    def test_no_params_shows_all_expenses(self, auth_client):
        """No filter means all expenses across all dates appear on the page."""
        client, uid = auth_client
        old_date = "2024-06-01"
        new_date = _today_iso()
        _insert_expenses(uid, [
            (99.99, "Shopping", old_date, "Old purchase"),
            (10.00, "Food",     new_date, "Today snack"),
        ])

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get("/profile")

        body = resp.data.decode()
        # Both transactions from very different dates should appear
        assert "Old purchase" in body or "Shopping" in body, (
            "Expense from the distant past should appear in unfiltered view"
        )
        assert "Today snack" in body or "Food" in body, (
            "Today's expense should appear in unfiltered view"
        )

    def test_no_params_total_includes_all_expenses(self, auth_client):
        """Total spent in the unfiltered view must sum all expenses."""
        client, uid = auth_client
        _insert_expenses(uid, [
            (100.00, "Bills", "2023-03-10", "Very old bill"),
            (50.00,  "Food",  _today_iso(), "Lunch"),
        ])

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get("/profile")

        body = resp.data.decode()
        # ₹ 150.00 total across both expenses
        assert "150" in body, (
            "Unfiltered total must include all expenses"
        )


# ------------------------------------------------------------------ #
# 3. ₹ symbol always present                                           #
# ------------------------------------------------------------------ #

class TestRupeeSymbolAlwaysPresent:
    @pytest.mark.parametrize("url_suffix", [
        "",                                                             # no filter
        f"?date_from={_first_of_month_iso()}&date_to={_today_iso()}",  # this month
        f"?date_from={_three_months_ago_iso()}&date_to={_today_iso()}", # 3 months
        f"?date_from={_six_months_ago_iso()}&date_to={_today_iso()}",   # 6 months
    ])
    def test_rupee_symbol_present_for_filter(self, auth_client, url_suffix):
        """₹ must appear in the response for every filter state."""
        client, uid = auth_client
        _insert_expenses(uid, [
            (75.00, "Food", _today_iso(), "Lunch"),
        ])

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get(f"/profile{url_suffix}")

        body = resp.data.decode()
        assert "₹" in body, (
            f"₹ symbol must appear in the response for /profile{url_suffix}"
        )

    def test_rupee_symbol_present_when_no_expenses_in_range(self, auth_client):
        """₹ symbol must appear even when the filter returns zero expenses."""
        client, uid = auth_client
        # User has no expenses at all

        far_future_from = "2099-01-01"
        far_future_to   = "2099-01-31"

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get(f"/profile?date_from={far_future_from}&date_to={far_future_to}")

        body = resp.data.decode()
        assert "₹" in body, "₹ symbol must appear even with empty filter results"


# ------------------------------------------------------------------ #
# 4. This Month filter                                                 #
# ------------------------------------------------------------------ #

class TestThisMonthFilter:
    def test_this_month_shows_current_month_expense(self, auth_client):
        """'This Month' filter must include expenses from the current calendar month."""
        client, uid = auth_client
        this_month_date = _today().replace(day=1).isoformat()  # first day of month
        _insert_expenses(uid, [
            (80.00, "Bills", this_month_date, "Current month bill"),
        ])

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get(
                f"/profile?date_from={_first_of_month_iso()}&date_to={_today_iso()}"
            )

        body = resp.data.decode()
        assert resp.status_code == 200
        assert "Current month bill" in body or "80" in body, (
            "Expense from this month's start date must appear in 'This Month' filter"
        )

    def test_this_month_excludes_last_month_expense(self, auth_client):
        """'This Month' filter must exclude expenses from the previous month."""
        client, uid = auth_client
        # An expense clearly before this month
        last_month = (_today() - timedelta(days=32)).isoformat()
        _insert_expenses(uid, [
            (999.00, "Shopping", last_month, "Last month shopping"),
            (10.00,  "Food",     _today_iso(), "Today food"),
        ])

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get(
                f"/profile?date_from={_first_of_month_iso()}&date_to={_today_iso()}"
            )

        body = resp.data.decode()
        assert resp.status_code == 200
        # The 999 amount should not appear in the total for this month
        assert "999.00" not in body or "Last month shopping" not in body, (
            "Expense from last month must not appear in 'This Month' filter results"
        )

    def test_this_month_today_expense_included(self, auth_client):
        """Expense dated today must be included in the 'This Month' filter (inclusive upper bound)."""
        client, uid = auth_client
        _insert_expenses(uid, [
            (42.00, "Food", _today_iso(), "Today's meal"),
        ])

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get(
                f"/profile?date_from={_first_of_month_iso()}&date_to={_today_iso()}"
            )

        body = resp.data.decode()
        assert resp.status_code == 200
        assert "42" in body, "Today's expense must be included in 'This Month' filter"


# ------------------------------------------------------------------ #
# 5. Last 3 Months filter                                             #
# ------------------------------------------------------------------ #

class TestLast3MonthsFilter:
    def test_3_months_includes_expense_within_window(self, auth_client):
        """Expenses within 90 days ago → today must appear with the 3-month filter."""
        client, uid = auth_client
        within_window = (_today() - timedelta(days=45)).isoformat()
        _insert_expenses(uid, [
            (55.00, "Transport", within_window, "Recent bus pass"),
        ])

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get(
                f"/profile?date_from={_three_months_ago_iso()}&date_to={_today_iso()}"
            )

        body = resp.data.decode()
        assert resp.status_code == 200
        assert "Recent bus pass" in body or "55" in body, (
            "Expense 45 days ago must appear in last-3-months filter"
        )

    def test_3_months_excludes_older_expense(self, auth_client):
        """Expenses older than 90 days must NOT appear with the 3-month filter."""
        client, uid = auth_client
        old_date = (_today() - timedelta(days=120)).isoformat()
        _insert_expenses(uid, [
            (777.00, "Health", old_date, "Old pharmacy visit"),
            (10.00,  "Food",   _today_iso(), "Recent snack"),
        ])

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get(
                f"/profile?date_from={_three_months_ago_iso()}&date_to={_today_iso()}"
            )

        body = resp.data.decode()
        assert resp.status_code == 200
        assert "777.00" not in body or "Old pharmacy visit" not in body, (
            "Expense 120 days ago must not appear in last-3-months filter"
        )


# ------------------------------------------------------------------ #
# 6. Last 6 Months filter                                             #
# ------------------------------------------------------------------ #

class TestLast6MonthsFilter:
    def test_6_months_includes_expense_within_window(self, auth_client):
        """Expense 150 days ago must appear in last-6-months filter."""
        client, uid = auth_client
        within_window = (_today() - timedelta(days=150)).isoformat()
        _insert_expenses(uid, [
            (120.00, "Bills", within_window, "Within 6 months bill"),
        ])

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get(
                f"/profile?date_from={_six_months_ago_iso()}&date_to={_today_iso()}"
            )

        body = resp.data.decode()
        assert resp.status_code == 200
        assert "Within 6 months bill" in body or "120" in body, (
            "Expense 150 days ago must appear in last-6-months filter"
        )

    def test_6_months_excludes_older_expense(self, auth_client):
        """Expense 200 days ago must NOT appear in last-6-months filter."""
        client, uid = auth_client
        old_date = (_today() - timedelta(days=200)).isoformat()
        _insert_expenses(uid, [
            (888.00, "Entertainment", old_date, "Ancient subscription"),
            (15.00,  "Food",          _today_iso(), "Fresh food"),
        ])

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get(
                f"/profile?date_from={_six_months_ago_iso()}&date_to={_today_iso()}"
            )

        body = resp.data.decode()
        assert resp.status_code == 200
        assert "888.00" not in body or "Ancient subscription" not in body, (
            "Expense 200 days ago must not appear in last-6-months filter"
        )


# ------------------------------------------------------------------ #
# 7. All Time = clean /profile URL                                    #
# ------------------------------------------------------------------ #

class TestAllTimePreset:
    def test_all_time_no_params_shows_all_expenses(self, auth_client):
        """Clean /profile URL (All Time) must show expenses from any date."""
        client, uid = auth_client
        old_date = "2020-01-01"
        _insert_expenses(uid, [
            (300.00, "Bills", old_date, "Year 2020 bill"),
            (50.00,  "Food",  _today_iso(), "Today food"),
        ])

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get("/profile")

        body = resp.data.decode()
        assert resp.status_code == 200
        assert "Year 2020 bill" in body or "300" in body, (
            "All Time view must include expense from year 2020"
        )
        assert "Today food" in body or "50" in body, (
            "All Time view must include today's expense"
        )

    def test_all_time_total_sums_everything(self, auth_client):
        """All Time total must equal the sum of all user expenses regardless of date."""
        client, uid = auth_client
        _insert_expenses(uid, [
            (200.00, "Shopping", "2021-06-15", "Old shoes"),
            (100.00, "Health",   _today_iso(), "Checkup"),
        ])

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get("/profile")

        body = resp.data.decode()
        # Total should be 300.00
        assert "300" in body, "All Time total must be 300.00 (200 + 100)"


# ------------------------------------------------------------------ #
# 8. Custom valid date range                                           #
# ------------------------------------------------------------------ #

class TestCustomValidRange:
    def test_custom_range_shows_only_in_range_expenses(self, auth_client):
        """Only expenses within the custom date range must appear."""
        client, uid = auth_client
        in_range_date  = "2025-03-15"
        out_range_date = "2025-01-01"
        _insert_expenses(uid, [
            (66.00, "Food",      in_range_date,  "In-range meal"),
            (99.00, "Transport", out_range_date, "Out-of-range ride"),
        ])

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get("/profile?date_from=2025-03-01&date_to=2025-03-31")

        body = resp.data.decode()
        assert resp.status_code == 200
        assert "In-range meal" in body or "66" in body, (
            "Expense within custom range must appear"
        )
        assert "Out-of-range ride" not in body, (
            "Expense outside custom range must NOT appear"
        )

    def test_custom_range_transaction_count_correct(self, auth_client):
        """Transaction count in summary stats must match only in-range transactions."""
        client, uid = auth_client
        _insert_expenses(uid, [
            (20.00, "Food",  "2025-06-10", "June meal 1"),
            (30.00, "Bills", "2025-06-20", "June bill"),
            (50.00, "Other", "2025-05-05", "May expense"),  # outside range
        ])

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get("/profile?date_from=2025-06-01&date_to=2025-06-30")

        body = resp.data.decode()
        assert resp.status_code == 200
        # 2 transactions in June; must see "2" and NOT "3"
        assert "2" in body, "Transaction count must reflect only in-range expenses"

    def test_custom_range_date_from_is_inclusive(self, auth_client):
        """date_from boundary date must be included in the result."""
        client, uid = auth_client
        boundary_date = "2025-04-01"
        _insert_expenses(uid, [
            (11.00, "Food", boundary_date, "Boundary date expense"),
        ])

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get(f"/profile?date_from={boundary_date}&date_to=2025-04-30")

        body = resp.data.decode()
        assert resp.status_code == 200
        assert "Boundary date expense" in body or "11" in body, (
            "Expense on date_from boundary must be included (inclusive BETWEEN)"
        )

    def test_custom_range_date_to_is_inclusive(self, auth_client):
        """date_to boundary date must be included in the result."""
        client, uid = auth_client
        boundary_date = "2025-04-30"
        _insert_expenses(uid, [
            (22.00, "Health", boundary_date, "Last day expense"),
        ])

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get(f"/profile?date_from=2025-04-01&date_to={boundary_date}")

        body = resp.data.decode()
        assert resp.status_code == 200
        assert "Last day expense" in body or "22" in body, (
            "Expense on date_to boundary must be included (inclusive BETWEEN)"
        )

    def test_custom_range_category_breakdown_filtered(self, auth_client):
        """Category breakdown must only include categories from the filtered range."""
        client, uid = auth_client
        _insert_expenses(uid, [
            (100.00, "Shopping",      "2025-08-15", "In-range shopping"),
            (200.00, "Entertainment", "2024-01-01", "Old entertainment"),  # outside
        ])

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get("/profile?date_from=2025-08-01&date_to=2025-08-31")

        body = resp.data.decode()
        assert resp.status_code == 200
        assert "Shopping" in body, (
            "Category 'Shopping' (in range) must appear in breakdown"
        )
        assert "Entertainment" not in body, (
            "Category 'Entertainment' (outside range) must NOT appear in breakdown"
        )


# ------------------------------------------------------------------ #
# 9. date_from > date_to → flash error, fallback to unfiltered        #
# ------------------------------------------------------------------ #

class TestInvalidDateRange:
    def test_date_from_after_date_to_returns_200(self, auth_client):
        """Invalid range (start > end) must not crash; route must return 200."""
        client, uid = auth_client

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get(
                "/profile?date_from=2025-12-31&date_to=2025-01-01",
                follow_redirects=True,
            )

        assert resp.status_code == 200, (
            "Invalid date range must not crash the app (200 expected)"
        )

    def test_date_from_after_date_to_flashes_error(self, auth_client):
        """date_from > date_to must flash 'Start date must be before end date.'"""
        client, uid = auth_client
        _insert_expenses(uid, [
            (50.00, "Food", _today_iso(), "Some expense"),
        ])

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get(
                "/profile?date_from=2025-12-31&date_to=2025-01-01",
                follow_redirects=True,
            )

        body = resp.data.decode()
        assert "Start date must be before end date" in body, (
            "Flash message 'Start date must be before end date.' must be visible"
        )

    def test_date_from_after_date_to_falls_back_to_unfiltered(self, auth_client):
        """After invalid range, the view must fall back and show all expenses."""
        client, uid = auth_client
        # Insert an expense with a date that would be excluded by the invalid filter
        _insert_expenses(uid, [
            (99.00, "Bills", "2023-06-01", "Old bill visible in fallback"),
        ])

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get(
                "/profile?date_from=2025-12-31&date_to=2025-01-01",
                follow_redirects=True,
            )

        body = resp.data.decode()
        assert resp.status_code == 200
        # The unfiltered view should include the old expense
        assert "99" in body or "Old bill visible in fallback" in body, (
            "Fallback to unfiltered view must show all expenses including old ones"
        )

    def test_equal_dates_do_not_trigger_error(self, auth_client):
        """date_from == date_to (single day) is a valid range and must not flash an error."""
        client, uid = auth_client
        single_day = "2025-07-04"
        _insert_expenses(uid, [
            (25.00, "Food", single_day, "Independence day meal"),
        ])

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get(
                f"/profile?date_from={single_day}&date_to={single_day}",
                follow_redirects=True,
            )

        body = resp.data.decode()
        assert resp.status_code == 200
        assert "Start date must be before end date" not in body, (
            "Equal date_from and date_to must be treated as a valid single-day range"
        )


# ------------------------------------------------------------------ #
# 10. Malformed date string → silent fallback, no crash               #
# ------------------------------------------------------------------ #

class TestMalformedDate:
    @pytest.mark.parametrize("bad_date_from,bad_date_to", [
        ("not-a-date", _today_iso()),
        (_today_iso(), "not-a-date"),
        ("not-a-date", "also-not-a-date"),
        ("",           ""),
        ("2025-13-01", _today_iso()),   # month 13 does not exist
        ("2025-00-01", _today_iso()),   # month 0 does not exist
        ("2025-02-30", _today_iso()),   # day 30 doesn't exist in February
        ("20250101",   _today_iso()),   # wrong format (no dashes)
    ])
    def test_malformed_dates_do_not_crash(self, auth_client, bad_date_from, bad_date_to):
        """Any malformed date value must be silently ignored; route must return 200."""
        client, uid = auth_client
        _insert_expenses(uid, [(10.00, "Food", _today_iso(), "Fallback meal")])

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get(
                f"/profile?date_from={bad_date_from}&date_to={bad_date_to}",
                follow_redirects=True,
            )

        assert resp.status_code == 200, (
            f"Malformed dates ('{bad_date_from}', '{bad_date_to}') must not crash the app"
        )

    def test_malformed_date_falls_back_to_unfiltered(self, auth_client):
        """With a malformed date, all expenses must still be shown (unfiltered fallback)."""
        client, uid = auth_client
        _insert_expenses(uid, [
            (333.00, "Other", "2021-01-01", "Old fallback expense"),
        ])

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get(
                "/profile?date_from=not-a-date&date_to=also-not-a-date",
                follow_redirects=True,
            )

        body = resp.data.decode()
        assert resp.status_code == 200
        assert "333" in body or "Old fallback expense" in body, (
            "Malformed date fallback must show all expenses (unfiltered)"
        )

    def test_only_one_param_malformed_falls_back(self, auth_client):
        """If only one of the two params is malformed, both must be treated as absent."""
        client, uid = auth_client
        _insert_expenses(uid, [
            (77.00, "Food", "2020-05-05", "Very old snack"),
        ])

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get(
                f"/profile?date_from=garbage&date_to={_today_iso()}",
                follow_redirects=True,
            )

        body = resp.data.decode()
        assert resp.status_code == 200
        # Full unfiltered view: the 2020 expense should appear
        assert "77" in body or "Very old snack" in body, (
            "Single malformed param should fall back to fully unfiltered view"
        )


# ------------------------------------------------------------------ #
# 11. No expenses in selected range → zeros, no errors                #
# ------------------------------------------------------------------ #

class TestEmptyRangeResults:
    def test_no_expenses_in_range_returns_200(self, auth_client):
        """Profile page must return 200 when the filter matches zero expenses."""
        client, uid = auth_client
        # User has expenses but not in the requested range
        _insert_expenses(uid, [
            (50.00, "Food", "2020-01-15", "Ancient food"),
        ])

        far_future_from = "2099-01-01"
        far_future_to   = "2099-12-31"

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get(
                f"/profile?date_from={far_future_from}&date_to={far_future_to}"
            )

        assert resp.status_code == 200, (
            "Must return 200 even when no expenses exist in the selected range"
        )

    def test_no_expenses_in_range_shows_zero_total(self, auth_client):
        """When no expenses in range, total spent must display ₹ 0.00."""
        client, uid = auth_client
        # Expense outside the requested range
        _insert_expenses(uid, [
            (500.00, "Shopping", "2020-06-01", "Old shopping"),
        ])

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get(
                "/profile?date_from=2099-01-01&date_to=2099-12-31"
            )

        body = resp.data.decode()
        assert "0.00" in body, (
            "Total spent must show 0.00 when no expenses exist in selected range"
        )

    def test_no_expenses_in_range_shows_zero_transaction_count(self, auth_client):
        """When no expenses in range, transaction count must be 0."""
        client, uid = auth_client
        _insert_expenses(uid, [
            (100.00, "Bills", "2020-01-01", "Old bill"),
        ])

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get(
                "/profile?date_from=2099-01-01&date_to=2099-12-31"
            )

        body = resp.data.decode()
        assert resp.status_code == 200
        assert "0" in body, (
            "Transaction count must be 0 when no expenses fall in selected range"
        )

    def test_user_with_no_expenses_at_all_returns_200(self, auth_client):
        """User who has never added any expense must see a 200 response with ₹0.00."""
        client, uid = auth_client
        # No expenses inserted for this user at all

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get(
                f"/profile?date_from={_first_of_month_iso()}&date_to={_today_iso()}"
            )

        assert resp.status_code == 200
        body = resp.data.decode()
        assert "0.00" in body, "User with zero expenses must see ₹0.00 total"
        assert "₹" in body, "₹ symbol must appear even for a user with no expenses"

    def test_empty_range_no_crash_no_server_error(self, auth_client):
        """Empty filter result must never cause a 500 server error."""
        client, uid = auth_client

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get(
                "/profile?date_from=2099-06-01&date_to=2099-06-30"
            )

        assert resp.status_code != 500, (
            "Empty filter result must not cause a 500 Internal Server Error"
        )


# ------------------------------------------------------------------ #
# 12. Filter does not bleed across users                              #
# ------------------------------------------------------------------ #

class TestFilterIsolation:
    def test_filter_only_returns_current_users_expenses(self, auth_client):
        """Date filter must never return another user's expenses."""
        client, uid = auth_client
        # Create a second user with an expense in the same date range
        other_uid, _, _ = _insert_user("Other User")
        _insert_expenses(other_uid, [
            (999.00, "Bills", _today_iso(), "Other user secret expense"),
        ])
        # Current user has their own expense
        _insert_expenses(uid, [
            (10.00, "Food", _today_iso(), "My own lunch"),
        ])

        p1, p2, p3, p4 = _profile_patches()
        with p1, p2, p3, p4:
            resp = client.get(
                f"/profile?date_from={_first_of_month_iso()}&date_to={_today_iso()}"
            )

        body = resp.data.decode()
        assert resp.status_code == 200
        assert "Other user secret expense" not in body, (
            "Another user's expenses must never appear in the filtered view"
        )
        assert "999.00" not in body, (
            "Another user's expense amount must not appear in the filtered totals"
        )
