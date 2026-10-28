from decimal import Decimal, InvalidOperation
import secrets

from flask import Flask, render_template, request

from database import get_db

app = Flask(__name__)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        mobile = request.form.get("mobile", "").strip()
        email = request.form.get("email", "").strip()
        city = request.form.get("city", "").strip()

        if not first_name or not mobile or not email or not city:
            return render_template(
                "register.html",
                message="Please complete all required fields.",
            ), 400

        connection = None
        cursor = None
        try:
            connection = get_db()
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO customer
                    (first_name, last_name, mobile, email, city, registration_date)
                VALUES (%s, %s, %s, %s, %s, CURDATE())
                """,
                (first_name, last_name or None, mobile, email, city),
            )
            connection.commit()
            return render_template(
                "register.html",
                message="Customer registered successfully.",
            )
        except Exception:
            if connection:
                connection.rollback()
            app.logger.exception("Customer registration failed")
            return render_template(
                "register.html",
                message="Unable to register the customer. Check the server log for details.",
            ), 500
        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()

    return render_template("register.html")


@app.route("/customers")
def customers():
    connection = None
    cursor = None
    try:
        connection = get_db()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT customer_id, first_name, last_name,
                   mobile, email, city
            FROM customer
            ORDER BY customer_id DESC
            """
        )
        return render_template("customers.html", customers=cursor.fetchall())
    except Exception:
        app.logger.exception("Could not load customers")
        return "Unable to load customers. Check the server log for details.", 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route("/account", methods=["GET", "POST"])
def create_account():
    if request.method == "POST":
        try:
            customer_id = int(request.form.get("customer_id", ""))
            branch_id = int(request.form.get("branch_id", ""))
            balance = Decimal(request.form.get("balance", ""))
        except (InvalidOperation, ValueError):
            return render_template(
                "account.html",
                message="Enter valid customer, branch, and balance values.",
            ), 400

        account_type = request.form.get("account_type", "")
        if account_type not in {"Saving", "Current", "Salary"}:
            return render_template(
                "account.html",
                message="Select a valid account type.",
            ), 400
        if not balance.is_finite() or balance < 0:
            return render_template(
                "account.html",
                message="Opening balance must be zero or greater.",
            ), 400

        connection = None
        cursor = None
        try:
            connection = get_db()
            cursor = connection.cursor()

            cursor.execute(
                "SELECT customer_id FROM customer WHERE customer_id = %s",
                (customer_id,),
            )
            if not cursor.fetchone():
                return render_template(
                    "account.html",
                    message="Customer ID not found. Please enter a valid customer ID.",
                ), 400

            cursor.execute(
                "SELECT branch_id FROM branch WHERE branch_id = %s",
                (branch_id,),
            )
            if not cursor.fetchone():
                return render_template(
                    "account.html",
                    message="Branch ID not found. Please select a valid branch.",
                ), 400

            account_number = "KASHI" + secrets.token_hex(6).upper()
            cursor.execute(
                """
                INSERT INTO account
                    (account_number, account_type, opening_date,
                     balance, status, branch_id)
                VALUES (%s, %s, CURDATE(), %s, 'Active', %s)
                """,
                (account_number, account_type, balance, branch_id),
            )
            account_id = cursor.lastrowid
            cursor.execute(
                """
                INSERT INTO account_holder
                    (customer_id, account_id, holder_since, holder_type)
                VALUES (%s, %s, CURDATE(), 'Primary')
                """,
                (customer_id, account_id),
            )
            connection.commit()
            return render_template(
                "account.html",
                message=f"Account created successfully! Account Number: {account_number}",
            )
        except Exception:
            if connection:
                connection.rollback()
            app.logger.exception("Account creation failed")
            return render_template(
                "account.html",
                message="Unable to create the account. Check the server log for details.",
            ), 500
        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()

    return render_template("account.html")


def parse_positive_amount(value):
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError):
        return None

    if not amount.is_finite() or amount <= 0:
        return None
    return amount


def update_account_balance(transaction_type, page_title):
    if request.method == "POST":
        account_number = request.form.get("account_number", "").strip()
        amount = parse_positive_amount(request.form.get("amount", ""))
        if not account_number or amount is None:
            return render_template(
                "money.html",
                page_title=page_title,
                endpoint=request.endpoint,
                message="Enter a valid account number and an amount greater than zero.",
            ), 400

        connection = None
        cursor = None
        try:
            connection = get_db()
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT account_id, balance
                FROM account
                WHERE account_number = %s AND status = 'Active'
                FOR UPDATE
                """,
                (account_number,),
            )
            account = cursor.fetchone()
            if not account:
                return render_template(
                    "money.html",
                    page_title=page_title,
                    endpoint=request.endpoint,
                    message="Active account not found.",
                ), 404

            account_id, current_balance = account
            current_balance = Decimal(current_balance)
            if transaction_type == "WITHDRAWAL" and current_balance < amount:
                return render_template(
                    "money.html",
                    page_title=page_title,
                    endpoint=request.endpoint,
                    message="Insufficient funds for this withdrawal.",
                ), 400

            new_balance = (
                current_balance + amount
                if transaction_type == "DEPOSIT"
                else current_balance - amount
            )
            reference_number = secrets.token_hex(10).upper()
            cursor.execute(
                "UPDATE account SET balance = %s WHERE account_id = %s",
                (new_balance, account_id),
            )
            cursor.execute(
                """
                INSERT INTO bank_transaction
                    (account_id, transaction_type, amount, description, reference_number)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    account_id,
                    transaction_type,
                    amount,
                    page_title,
                    reference_number,
                ),
            )
            connection.commit()
            message = (
                f"{page_title} successful. Reference: {reference_number}. "
                f"New balance: {new_balance:.2f}"
            )
            return render_template(
                "money.html",
                page_title=page_title,
                endpoint=request.endpoint,
                message=message,
            )
        except Exception:
            if connection:
                connection.rollback()
            app.logger.exception("%s failed", page_title)
            return render_template(
                "money.html",
                page_title=page_title,
                endpoint=request.endpoint,
                message=f"Unable to complete the {page_title.lower()}. Check the server log for details.",
            ), 500
        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()

    return render_template(
        "money.html",
        page_title=page_title,
        endpoint=request.endpoint,
    )


@app.route("/deposit", methods=["GET", "POST"])
def deposit():
    return update_account_balance("DEPOSIT", "Deposit")


@app.route("/withdraw", methods=["GET", "POST"])
def withdraw():
    return update_account_balance("WITHDRAWAL", "Withdrawal")


@app.route("/transfer", methods=["GET", "POST"])
def transfer():
    if request.method == "POST":
        source_number = request.form.get("source_account_number", "").strip()
        destination_number = request.form.get(
            "destination_account_number", ""
        ).strip()
        amount = parse_positive_amount(request.form.get("amount", ""))
        if (
            not source_number
            or not destination_number
            or source_number == destination_number
            or amount is None
        ):
            return render_template(
                "transfer.html",
                message="Enter two different account numbers and an amount greater than zero.",
            ), 400

        connection = None
        cursor = None
        try:
            connection = get_db()
            cursor = connection.cursor()
            locked_accounts = {}
            for number in sorted((source_number, destination_number)):
                cursor.execute(
                    """
                    SELECT account_id, balance
                    FROM account
                    WHERE account_number = %s AND status = 'Active'
                    FOR UPDATE
                    """,
                    (number,),
                )
                account = cursor.fetchone()
                if not account:
                    return render_template(
                        "transfer.html",
                        message=f"Active account not found: {number}",
                    ), 404
                locked_accounts[number] = account

            source_id, source_balance = locked_accounts[source_number]
            destination_id, destination_balance = locked_accounts[destination_number]
            source_balance = Decimal(source_balance)
            destination_balance = Decimal(destination_balance)
            if source_balance < amount:
                return render_template(
                    "transfer.html",
                    message="Insufficient funds for this transfer.",
                ), 400

            reference_number = secrets.token_hex(10).upper()
            cursor.execute(
                "UPDATE account SET balance = %s WHERE account_id = %s",
                (source_balance - amount, source_id),
            )
            cursor.execute(
                "UPDATE account SET balance = %s WHERE account_id = %s",
                (destination_balance + amount, destination_id),
            )
            cursor.executemany(
                """
                INSERT INTO bank_transaction
                    (account_id, transaction_type, amount, description, reference_number)
                VALUES (%s, %s, %s, %s, %s)
                """,
                [
                    (
                        source_id,
                        "TRANSFER_OUT",
                        amount,
                        f"Transfer to {destination_number}",
                        reference_number,
                    ),
                    (
                        destination_id,
                        "TRANSFER_IN",
                        amount,
                        f"Transfer from {source_number}",
                        reference_number,
                    ),
                ],
            )
            connection.commit()
            return render_template(
                "transfer.html",
                message=f"Transfer successful. Reference: {reference_number}",
            )
        except Exception:
            if connection:
                connection.rollback()
            app.logger.exception("Transfer failed")
            return render_template(
                "transfer.html",
                message="Unable to complete the transfer. Check the server log for details.",
            ), 500
        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()

    return render_template("transfer.html")


@app.route("/transactions")
def transactions():
    connection = None
    cursor = None
    try:
        connection = get_db()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT t.transaction_id, a.account_number, t.transaction_type,
                   t.amount, t.transaction_date, t.description,
                   t.reference_number, t.transaction_status
            FROM bank_transaction AS t
            JOIN account AS a ON a.account_id = t.account_id
            ORDER BY t.transaction_date DESC, t.transaction_id DESC
            """
        )
        return render_template("transactions.html", transactions=cursor.fetchall())
    except Exception:
        app.logger.exception("Could not load transactions")
        return "Unable to load transactions. Check the server log for details.", 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@app.route("/loans")
def loans():
    connection = None
    cursor = None
    try:
        connection = get_db()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT l.loan_id, l.customer_id,
                   CONCAT(c.first_name, ' ', COALESCE(c.last_name, '')) AS customer_name,
                   l.loan_type, l.loan_amount, l.interest_rate,
                   l.start_date, l.tenure_months, l.loan_status,
                   b.branch_name
            FROM loan AS l
            JOIN customer AS c ON c.customer_id = l.customer_id
            JOIN branch AS b ON b.branch_id = l.branch_id
            ORDER BY l.loan_id DESC
            """
        )
        return render_template("loans.html", loans=cursor.fetchall())
    except Exception:
        app.logger.exception("Could not load loans")
        return "Unable to load loans. Check the server log for details.", 500
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


if __name__ == "__main__":
    app.run(debug=True)
