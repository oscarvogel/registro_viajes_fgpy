import mysql.connector
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def check_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")

    # Parse the URL
    # mysql+mysqlconnector://user:pass@host/db
    url = DATABASE_URL.replace("mysql+mysqlconnector://", "")
    user_pass, host_db = url.split("@")
    user, password = user_pass.split(":", 1)
    host, db = host_db.split("/", 1)

    conn = mysql.connector.connect(
        host=host,
        user=user,
        password=password,
        database=db
    )
    conn.close()


if __name__ == "__main__":
    try:
        check_connection()
        print("Connection successful")
    except Exception as e:
        print(f"Connection failed: {e}")
