import os
import sqlite3
from datetime import date, datetime, timedelta

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash
from database.db import get_db, init_db, seed_db, create_user, get_user_by_email
from database.queries import (
    get_user_by_id,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(32)

# ------------------------------------------------------------------ #
# Database initialisation                                             #
# ------------------------------------------------------------------ #

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

def _parse_date(raw):
    """Return an ISO date string 'YYYY-MM-DD' or None on bad/missing input.

    Validates format via strptime so malformed values never reach the DB.
    """
    if not raw or len(raw) != 10:
        return None
    try:
        datetime.strptime(raw, "%Y-%m-%d")
        return raw
    except ValueError:
        return None


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("register.html")

    # ── Read form fields ──────────────────────────────────────────────
    name             = request.form.get("name", "").strip()
    email            = request.form.get("email", "").strip().lower()
    password         = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    # ── Validate ──────────────────────────────────────────────────────
    if not all([name, email, password, confirm_password]):
        flash("All fields are required.")
        return render_template("register.html")

    if password != confirm_password:
        flash("Passwords do not match.")
        return render_template("register.html")

    if len(password) < 8:
        flash("Password must be at least 8 characters.")
        return render_template("register.html")

    # ── Insert ────────────────────────────────────────────────────────
    try:
        create_user(name, email, password)
    except sqlite3.IntegrityError:
        flash("An account with that email already exists.")
        return render_template("register.html")

    flash("Account created! Please log in.")
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("login.html")

    # ── Read form fields ──────────────────────────────────────────────
    email    = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    # ── Look up user ──────────────────────────────────────────────────
    user = get_user_by_email(email)

    # ── Verify password (generic error to avoid user enumeration) ─────
    if user is None or not check_password_hash(user["password_hash"], password):
        flash("Invalid email or password.")
        return render_template("login.html")

    # ── Successful login ──────────────────────────────────────────────
    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    return redirect(url_for("profile"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    uid  = session["user_id"]
    user = get_user_by_id(uid)

    if user is None:                         # stale session — user no longer in DB
        session.clear()
        return redirect(url_for("login"))

    # ── Parse & validate query params ──────────────────────────────────
    date_from = _parse_date(request.args.get("date_from"))
    date_to   = _parse_date(request.args.get("date_to"))

    # If only one bound is supplied, treat both as absent (spec §Rules)
    if bool(date_from) != bool(date_to):
        date_from = date_to = None

    # Guard: start must not be after end
    if date_from and date_to and date_from > date_to:
        flash("Start date must be before end date.")
        date_from = date_to = None

    # ── Compute preset ranges in Python (never in the template) ──────────
    today            = date.today()
    today_iso        = today.isoformat()
    first_of_month   = today.replace(day=1).isoformat()
    three_months_ago = (today - timedelta(days=90)).isoformat()
    six_months_ago   = (today - timedelta(days=180)).isoformat()

    # Determine which preset button to highlight
    if date_from is None and date_to is None:
        active_preset = "all"
    elif date_from == first_of_month and date_to == today_iso:
        active_preset = "this_month"
    elif date_from == three_months_ago and date_to == today_iso:
        active_preset = "3months"
    elif date_from == six_months_ago and date_to == today_iso:
        active_preset = "6months"
    else:
        active_preset = "custom"

    # ── Live DB queries (all respect the active date range) ─────────────
    raw_stats = get_summary_stats(uid, date_from=date_from, date_to=date_to)
    raw_txns  = get_recent_transactions(uid, limit=10, date_from=date_from, date_to=date_to)
    raw_cats  = get_category_breakdown(uid, date_from=date_from, date_to=date_to)

    # ── Format for template ─────────────────────────────────────────────
    stats = {
        "total_spent":       f"₹ {raw_stats['total_spent']:,.2f}",
        "transaction_count": raw_stats["transaction_count"],
        "top_category":      raw_stats["top_category"],
    }

    transactions = [
        {
            "date":        t["date"],
            "description": t["description"],
            "category":    t["category"],
            "amount":      f"₹ {t['amount']:,.2f}",
        }
        for t in raw_txns
    ]

    categories = [
        {
            "name":    c["name"],
            "amount":  f"₹ {c['amount']:,.2f}",
            "percent": c["pct"],
        }
        for c in raw_cats
    ]

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
        # filter state
        date_from=date_from or "",
        date_to=date_to or "",
        active_preset=active_preset,
        # preset URLs computed in Python via url_for
        preset_this_month=url_for("profile", date_from=first_of_month, date_to=today_iso),
        preset_3months=url_for("profile", date_from=three_months_ago, date_to=today_iso),
        preset_6months=url_for("profile", date_from=six_months_ago,   date_to=today_iso),
        preset_all=url_for("profile"),
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    _debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=_debug, port=5001)
