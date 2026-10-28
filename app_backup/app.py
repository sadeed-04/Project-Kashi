from flask import Flask, render_template
from database import get_db

app = Flask(__name__)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/register")
def register():
    return render_template("register.html")


@app.route("/test-db")
def test_db():
    connection = None
    cursor = None

    try:
        connection = get_db()
        cursor = connection.cursor()

        cursor.execute("SELECT COUNT(*) FROM customer")
        result = cursor.fetchone()

        return f"MySQL connected successfully! Total customers: {result[0]}"

    except Exception as error:
        return f"Database connection failed: {error}", 500

    finally:
        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()


if __name__ == "__main__":
    app.run(debug=True)