import os

from sqlalchemy import URL


def database_url():
    if os.getenv("PAYMENT_DATABASE_URL"):
        return os.environ["PAYMENT_DATABASE_URL"]
    return URL.create("postgresql+psycopg2", username=os.getenv("PAYMENT_DB_USER", "payment_app"),
                      password=os.environ["PAYMENT_DB_PASSWORD"], host=os.getenv("PAYMENT_DB_HOST", "payment-postgres"),
                      port=5432, database="payment_control")
