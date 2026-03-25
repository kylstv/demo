import os
import psycopg2
import psycopg2.extras
from psycopg2 import pool
from dotenv import load_dotenv

# Load .env (local only)
load_dotenv()

# Global connection pool
connection_pool = None


def init_db():
    """Initialize connection pool (call once on app start)."""
    global connection_pool

    db_url = os.environ.get("DATABASE_URL")

    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    try:
        if db_url:
            connection_pool = psycopg2.pool.SimpleConnectionPool(
                minconn=1,
                maxconn=10,
                dsn=db_url,
                sslmode="require",          # ✅ REQUIRED for Railway
                connect_timeout=10          # ✅ Prevent hanging
            )
        else:
            print("⚠️ Using local database config.")
            connection_pool = psycopg2.pool.SimpleConnectionPool(
                minconn=1,
                maxconn=5,
                host=os.getenv("DB_HOST", "localhost"),
                port=os.getenv("DB_PORT", 5432),
                dbname=os.getenv("DB_NAME", "claude"),
                user=os.getenv("DB_USER", "postgres"),
                password=os.getenv("DB_PASSWORD", ""),
                connect_timeout=10
            )

    except Exception as e:
        print(f"❌ DB INIT ERROR: {e}")
        raise e


def get_conn():
    """Get connection from pool."""
    if connection_pool is None:
        init_db()

    try:
        conn = connection_pool.getconn()

        # Ensure connection is alive (Railway sleep fix)
        with conn.cursor() as cur:
            cur.execute("SELECT 1")

        return conn

    except Exception:
        # Reconnect if broken
        init_db()
        return connection_pool.getconn()


def release_conn(conn):
    """Return connection to pool."""
    if connection_pool:
        connection_pool.putconn(conn)


def query(sql, params=None, fetchone=False, fetchall=False, commit=False):
    """Production-safe query helper."""
    conn = get_conn()

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params or ())

            if commit:
                conn.commit()
                return cur.rowcount

            if fetchone:
                return cur.fetchone()

            if fetchall:
                return cur.fetchall()

    except Exception as e:
        conn.rollback()
        print(f"❌ QUERY ERROR: {sql}")
        print(f"Details: {e}")
        raise e

    finally:
        release_conn(conn)