import os
import re

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
from decimal import Decimal

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    owned = db.execute("SELECT * FROM stock_totals WHERE user_id=?", session["user_id"])
    owned_info = []
    grand_total = 0.00
    cash_list = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])
    cash = cash_list[0]["cash"]
    for i in range(len(owned)):
        symbol = owned[i]["symbol"]
        shares = owned[i]["shares"]
        info = lookup(symbol)
        price = usd(float(info["price"]))
        total_value = float(info["price"]) * shares
        grand_total += float(total_value)
        total_value = usd(total_value)
        owned_info.append(
            {"symbol": symbol, "shares": shares, "price": price, "value": total_value}
        )
    total_total = usd(float(grand_total) + float(cash))
    grand_total = usd(grand_total)
    cash = usd(cash)
    return render_template(
        "/index.html",
        owned_info=owned_info,
        grand_total=grand_total,
        cash=cash,
        total_total=total_total,
    )


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")

    # If form submitted
    elif request.method == "POST":
        # set user id to variable
        user_id = session["user_id"]
        # get stock info
        info = lookup(request.form.get("symbol"))
        # check that shares is int (will be positive due to form min)
        try:
            shares = int(request.form.get("shares"))
        except:
            return apology("number of shares must be a positive integer", 400)
        if shares < 1:
            return apology("Number of shares must be a positive integer", 400)
        # assign SQL args to variables
        try:
            symbol = info["symbol"]
        except TypeError:
            return apology("stock does not exist", 400)
        price = float(info["price"])
        cash_list = db.execute("SELECT cash FROM users WHERE id=?", user_id)
        cash = float(cash_list[0]["cash"])
        # Check affordability
        if cash < price * shares:
            return apology("You're too broke, bruh", 400)
        # do cost math, subtract from user's cash
        cost = price * shares
        rounded_cost = f"{cost:.2f}"
        cash -= float(rounded_cost)
        # update cash value
        db.execute("UPDATE users SET cash=? WHERE id=?", cash, user_id)
        # get info on already owned shares of same company and determine if exists
        owned = db.execute(
            "SELECT * FROM stock_totals WHERE user_id=? AND symbol=?", user_id, symbol
        )
        try:
            total_shares = owned[0]["shares"] + shares
        # if user doesn't already own shares
        # create new rows in totals and transactions tables with info
        except IndexError:
            if len(owned) != 1:
                db.execute(
                    "INSERT INTO stock_totals(user_id, symbol, shares) VALUES (?, ?, ?)",
                    user_id,
                    symbol,
                    shares,
                )
                db.execute(
                    "INSERT INTO transactions (user_id, symbol, price, shares, transaction_type) VALUES(?, ?, ?, ?, ?)",
                    user_id,
                    symbol,
                    price,
                    shares,
                    0,
                )
                return redirect("/")
        # if user owns share(s) already
        # create new row in purchases table
        # update transactions total table
        db.execute(
            "INSERT INTO transactions (user_id, symbol, price, shares, transaction_type) VALUES(?, ?, ?, ?, ?)",
            user_id,
            symbol,
            price,
            shares,
            0,
        )
        db.execute(
            "UPDATE stock_totals SET shares=? WHERE user_id=? AND symbol=?",
            total_shares,
            user_id,
            symbol,
        )
        # send to homepage
        return redirect("/")


@app.route("/history")
@login_required
def history():
    purchases = db.execute(
        "SELECT * FROM transactions WHERE user_id=? AND transaction_type=0 ORDER BY transaction_time",
        session["user_id"],
    )
    sales = db.execute(
        "SELECT * FROM transactions WHERE user_id=? AND transaction_type=1 ORDER BY transaction_time",
        session["user_id"],
    )
    return render_template("/history.html", purchases=purchases, sales=sales)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 400)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/login")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")

    elif request.method == "POST":
        info = lookup(request.form.get("symbol"))
        try:
            symbol = info["name"]
        except TypeError:
            return apology("stock does not exist", 400)
        price = usd(info["price"])
        return render_template("quoted.html", symbol=symbol, price=price)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        password_pattern = (
            "^(?=.*?[A-Z])(?=.*?[a-z])(?=.*?[0-9])(?=.*?[#?!@$%^&*-]).{8,}$"
        )

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure confirmation was submitted
        elif not request.form.get("confirmation"):
            return apology("must confirm password", 400)

        # Ensure confirmation matches password
        elif not request.form.get("password") == request.form.get("confirmation"):
            return apology("password and confirmation do not match", 400)

        # Ensure password matches pattern
        elif not re.match(password_pattern, request.form.get("password")):
            return apology("password does not meet requirements", 400)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username doesn't exist
        if len(rows) != 1:
            db.execute(
                "INSERT INTO users (username, hash) VALUES(?, ?)",
                request.form.get("username"),
                generate_password_hash(
                    request.form.get("password"), method="sha256", salt_length=8
                ),
            )
        else:
            return apology("username already exists", 400)

        # Redirect user to login page
        return redirect("/login")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "GET":
        info = db.execute(
            "SELECT symbol FROM stock_totals WHERE user_id=?", session["user_id"]
        )
        symbols = []
        for inf in info:
            symbols.append(inf["symbol"])
        return render_template("sell.html", symbols=symbols)

    elif request.method == "POST":
        # Assign user_id and info to variables
        user_id = session["user_id"]
        info = lookup(request.form.get("symbol"))
        # Ensure shares is positive int
        try:
            shares = int(request.form.get("shares"))
        except:
            return apology("Number of shares must be a positive integer", 400)
        if shares < 1:
            return apology("Number of shares must be a positive integer", 400)
        # Get info from info var, assign to variables
        try:
            symbol = info["symbol"]
        except TypeError:
            return apology("Stock does not exist", 400)
        price = float(info["price"])
        owned = db.execute(
            "SELECT * FROM stock_totals WHERE user_id=? AND symbol=?", user_id, symbol
        )
        # check for enough shares
        try:
            if owned[0]["shares"] < shares:
                return apology("You don't own enough shares of that stock", 400)
        except IndexError:
            return apology("You don't own any shares of that stock", 400)
        # Subtract shares
        total_shares = owned[0]["shares"] - shares
        cash_list = db.execute("SELECT cash FROM users WHERE id=?", user_id)
        cash = float(cash_list[0]["cash"])
        sale_value = price * shares
        cash += sale_value
        cash = f"{cash:.2f}"
        db.execute("UPDATE users SET cash=? WHERE id=?", cash, user_id)
        db.execute(
            "INSERT INTO transactions (user_id, symbol, shares, price, transaction_type) VALUES(?, ?, ?, ?, ?)",
            user_id,
            symbol,
            shares,
            price,
            1,
        )
        db.execute(
            "UPDATE stock_totals SET shares=? WHERE user_id=? AND symbol=?",
            total_shares,
            user_id,
            symbol,
        )
        return redirect("/")
