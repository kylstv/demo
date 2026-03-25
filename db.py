import os
import psycopg2
from psycopg2 import pool

# Global variable for the pool
connection_pool = None

def init_db():
    global connection_pool
    # ALWAYS check the Environment Variable first
    db_url = os.environ.get("DB_URL")

    if db_url:
        print("✅ Connecting to Remote Railway Database via Environment Variable...")
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
    else:
        # If this prints, it means Step 2 below was not done correctly
        print("❌ CRITICAL ERROR: DATABASE_URL not found in Environment Variables!")
        return

    try:
        # Switching to ThreadedConnectionPool for better stability on Railway
        connection_pool = psycopg2.pool.ThreadedConnectionPool(
            1, 20, dsn=db_url
        )
        print("✅ Database Pool Initialized Successfully!")
    except Exception as e:
        print(f"❌ DB INIT ERROR: {e}")
        raise e

def get_db():
    global connection_pool
    if connection_pool is None:
        init_db()
    return connection_pool.getconn()

def release_db(conn):
    global connection_pool
    if connection_pool:
        connection_pool.putconn(conn)

def query(sql, params=(), fetchone=False, fetchall=False, commit=False):
    """The missing function that was causing your ImportError"""
    conn = get_db()
    try:
        # RealDictCursor makes results behave like dictionaries: row['name']
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            if commit:
                conn.commit()
                return cur.rowcount
            if fetchone:
                return cur.fetchone()
            if fetchall:
                return cur.fetchall()
    except Exception as e:
        print(f"❌ QUERY ERROR: {e}")
        raise e
    finally:
        release_db(conn)

# Import this at the top to make RealDictCursor work
import psycopg2.extras