import os
import psycopg2
import psycopg2.extras
from psycopg2 import pool
from dotenv import load_dotenv

# Load .env (local only)
load_dotenv()

connection_pool = None


def get_db():
    """Backward compatibility wrapper"""
    return get_conn()


def init_db():
    """Initialize connection pool (safe to call multiple times)."""
    global connection_pool

    if connection_pool is not None:
        return  # جلوگیری duplicate pool (IMPORTANT)

    db_url = os.environ.get("DATABASE_URL")

    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    try:
        if db_url:
            connection_pool = psycopg2.pool.SimpleConnectionPool(
                minconn=1,
                maxconn=10,
                dsn=db_url,
                sslmode="require",
                connect_timeout=10
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

        print("✅ Database pool initialized")

    except Exception as e:
        print(f"❌ DB INIT ERROR: {e}")
        raise e


def get_conn():
    """Get a healthy connection from pool."""
    global connection_pool

    if connection_pool is None:
        init_db()

    try:
        conn = connection_pool.getconn()

        # Check if connection is alive
        with conn.cursor() as cur:
            cur.execute("SELECT 1")

        return conn

    except Exception as e:
        print("⚠️ Connection stale. Reinitializing pool...", e)

        # HARD RESET pool (important for Railway sleep issues)
        try:
            if connection_pool:
                connection_pool.closeall()
        except Exception:
            pass

        connection_pool = None
        init_db()

        return connection_pool.getconn()


def release_conn(conn):
    """Return connection to pool safely."""
    try:
        if connection_pool and conn:
            connection_pool.putconn(conn)
    except Exception:
        pass  # don't crash app on release


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
        try:
            conn.rollback()
        except Exception:
            pass

        print(f"❌ QUERY ERROR: {sql}")
        print(f"Details: {e}")
        raise e

    finally:
        release_conn(conn)