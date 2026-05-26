import sqlite3

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash
from database.db import get_db, init_db, seed_db, create_user, get_user_by_email

app = Flask(__name__)
app.secret_key = "dev-secret-change-in-production"

# ------------------------------------------------------------------ #
# Database initialisation                                             #
# ------------------------------------------------------------------ #

with app.app_context():
    init_db()
    seed_db()


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

    user = {
        "name":         "Arjun Sharma",
        "email":        "arjun.sharma@example.com",
        "member_since": "January 2024",
    }

    stats = {
        "total_spent":       "₹ 24,350",
        "transaction_count": 47,
        "top_category":      "Food",
    }

    transactions = [
        {"date": "20 May 2025", "description": "Zomato Order",       "category": "Food",       "amount": "₹ 480"},
        {"date": "18 May 2025", "description": "Metro Card Recharge", "category": "Transport",  "amount": "₹ 200"},
        {"date": "15 May 2025", "description": "Amazon Purchase",     "category": "Shopping",   "amount": "₹ 1,299"},
        {"date": "12 May 2025", "description": "Electricity Bill",    "category": "Utilities",  "amount": "₹ 750"},
        {"date": "10 May 2025", "description": "Pharmacy",            "category": "Health",     "amount": "₹ 320"},
    ]

    categories = [
        {"name": "Food",       "amount": "₹ 8,200",  "percent": 75},
        {"name": "Shopping",   "amount": "₹ 6,450",  "percent": 59},
        {"name": "Transport",  "amount": "₹ 3,900",  "percent": 36},
        {"name": "Utilities",  "amount": "₹ 3,200",  "percent": 29},
        {"name": "Health",     "amount": "₹ 2,600",  "percent": 24},
    ]

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
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
    app.run(debug=True, port=5001)
