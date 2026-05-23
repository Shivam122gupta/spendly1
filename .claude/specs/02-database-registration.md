# Spec: Registration

## Overview
Implement user registration so new visitors can create a Spendly account. This step upgrades the existing stub `GET /register` route into a fully functional form that accepts a POST, validates input, hashes the password, and inserts a new row into the `users` table. On success the user is shown with a success message and then redirected to the login page. This is the entry point for all authenticated features that follow.

## Depends on
- Step 01 — Database setup (`users` table, `get_db()`)

## Routes
- `GET /register` — render registration form — public (already exists as stub, upgrade it)
- `POST /register` — process registration form, insert user, redirect to `/login` — public

## Database changes

No new tables or columns. The existing `users` table (`id`, `name`, `email`, `password_hash`, `created_at`) covers all requirements.

A new DB helper must be added to `database/db.py`:
- `create_user(name, email, password)` — hashes the password with `werkzeug`, inserts a row into `users`, returns the new user's `id`. Raises `sqlite3.IntegrityError` if the email is already taken (UNIQUE constraint).
## Templates

- **Modify**: `templates/register.html`
  - Change the form `action` to `url_for('register')` with `method="post"`
  - Add `name` attributes to all inputs:
    `name`, `email`, `password`, `confirm_password`
  - Add a block to display a flash error message (e.g. "Email already registered", "Passwords do not match")
  - Keep all existing visual design

## Files to change
- `app.py` — upgrade `register()` to handle `GET` and `POST`; add flash + redirect logic
- `database/db.py` — add `create_user()` helper
- `templates/register.html` — wire up form action/method and flash message display

## Files to create
None