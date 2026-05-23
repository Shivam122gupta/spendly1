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
        return redirect(url_for("landing"))

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
        return redirect(url_for("landing"))

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
    return redirect(url_for("landing"))


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
    return "Profile page — coming in Step 4"


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
