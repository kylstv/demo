import os
import psycopg2
from psycopg2 import pool

# Global variable for the pool
connection_pool = None

def init_db():
    global connection_pool
    # RAILWAY provides DATABASE_URL automatically if you link services
    db_url = os.environ.get("DATABASE_URL")

    if db_url:
        print("✅ Connecting to Remote Railway Database...")
        # Fix for newer SQLAlchemy/psycopg2 requirements
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
    else:
        print("⚠️ DATABASE_URL not found! Falling back to local...")
        db_url = "postgresql://postgres:szthvcPFInZUFrQYIvLtHShoUOUXWwRC@crossover.proxy.rlwy.net:38276/railway"

    try:
        connection_pool = psycopg2.pool.SimpleConnectionPool(
            1, 20, dsn=db_url
        )
    except Exception as e:
        print(f"❌ DB INIT ERROR: {e}")
        raise e

def get_db():
    if connection_pool is None:
        init_db()
    return connection_pool.getconn()