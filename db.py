import os
import psycopg2
from psycopg2 import pool
import psycopg2.extras

# Global variable for the pool
connection_pool = None

def init_db():
    global connection_pool
    # This grabs the internal ${{Postgres.DATABASE_URL}} you just set
    db_url = os.environ.get("DATABASE_URL")

    if not db_url:
        print("❌ ERROR: DATABASE_URL not found in Railway Dashboard!")
        return False

    # Standardize the prefix
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    try:
        # The 'dsn' contains the correct host, port, and password automatically
        connection_pool = psycopg2.pool.ThreadedConnectionPool(1, 20, dsn=db_url)
        print("✅ SUCCESS: Connected to Internal Railway Database!")
        return True
    except Exception as e:
        print(f"❌ CONNECTION FAILED: {e}")
        return False

def get_db():
    global connection_pool
    # If the pool doesn't exist, try to start it
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
    Utility function to run SQL queries.
    Returns results as dictionaries (e.g., row['name'] instead of row[0]).
    """
    conn = None
    try:
        conn = get_db()
        # Using RealDictCursor makes development much easier
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