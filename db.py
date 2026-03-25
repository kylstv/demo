import os
import psycopg2
from psycopg2 import pool
import psycopg2.extras

# Global variable for the pool
connection_pool = None

def init_db():
    global connection_pool
    
    # Priority 1: Check DATABASE_URL (Railway standard)
    # Priority 2: Check DB_URL (Your custom name)
    db_url = os.environ.get("DATABASE_URL") or os.environ.get("DB_URL")

    if not db_url:
        print("❌ CRITICAL ERROR: No Database URL found in Environment Variables!")
        return False

    # Fix for SQLAlchemy/Psycopg2 prefix requirements
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    try:
        # Use ThreadedConnectionPool for better stability in web environments
        connection_pool = psycopg2.pool.ThreadedConnectionPool(
            1, 20, dsn=db_url
        )
        print("✅ Database Pool Initialized Successfully!")
        return True
    except Exception as e:
        print(f"❌ DB INIT ERROR: {e}")
        connection_pool = None # Ensure it stays None if it fails
        return False

def get_db():
    global connection_pool
    # If pool is missing, try to initialize it once
    if connection_pool is None:
        if not init_db():
            raise Exception("Database could not be initialized. Check your Railway Environment Variables.")
    
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
    """Executes SQL queries and returns results as dictionaries."""
    conn = get_db()
    try:
        # RealDictCursor allows row['column_name'] access
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
        # If there's a database error, rollback the transaction
        if conn:
            conn.rollback()
        print(f"❌ QUERY ERROR: {e}")
        raise e
    finally:
        if conn:
            release_db(conn)