import mysql.connector


def get_db():
    connection = mysql.connector.connect(
        host="localhost",
        user="root",
        password="Shadeed@1234",
        database="kashi_bank"
    )

    return connection