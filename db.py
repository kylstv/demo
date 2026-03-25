import os
import psycopg2
from psycopg2 import pool
import psycopg2.extras

# Global connection pool
connection_pool = None


def init_db():
    global connection_pool

    db_url = os.environ.get("DATABASE_URL")

    if not db_url:
        print("❌ ERROR: DATABASE_URL not found in environment!")
        return False

    # Fix deprecated prefix
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    try:
        # Initialize connection pool with SSL (REQUIRED for Railway)
        connection_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=20,
            dsn=db_url,
            sslmode="require",
            connect_timeout=10
        )

        print("✅ SUCCESS: Connected to Railway PostgreSQL!")
        return True

    except Exception as e:
        print(f"❌ CONNECTION FAILED: {e}")
        return False


def get_db():
    global connection_pool

    # Initialize pool if not already
    if connection_pool is None:
        success = init_db()
        if not success:
            raise Exception("Database could not be initialized. Check Railway Variables.")

    try:
        return connection_pool.getconn()
    except Exception as e:
        print(f"❌ Error getting connection from pool: {e}")
        raise e


def release_db(conn):
    global connection_pool

    if connection_pool and conn:
        try:
            connection_pool.putconn(conn)
        except Exception as e:
            print(f"❌ Error releasing connection: {e}")


def query(sql, params=(), fetchone=False, fetchall=False, commit=False):
    """
    Run SQL queries with optional fetch/commit.
    Returns dict results (column-based).
    """
    conn = None

    try:
        conn = get_db()

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)

            if commit:
                conn.commit()
                return cur.rowcount

            if fetchone:
                return cur.fetchone()

            if fetchall:
                return cur.fetchall()

            return None

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ QUERY ERROR: {e}")
        raise e

    finally:
        if conn:
            release_db(conn)


def close_all_connections():
    """
    Gracefully close all connections (optional for shutdown).
    """
    global connection_pool

    if connection_pool:
        connection_pool.closeall()
        print("🔒 All DB connections closed.")