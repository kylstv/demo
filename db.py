import os
import psycopg2
from psycopg2 import pool
import psycopg2.extras

# Global variable for the pool
connection_pool = None

def init_db():
    global connection_pool
    
    # 1. Grab the official Railway variable. 
    # If this is missing, the app will fail gracefully with a clear message.
    db_url = os.environ.get("DATABASE_URL")

    if not db_url:
        print("❌ CRITICAL ERROR: DATABASE_URL not found in Environment Variables!")
        print("👉 FIX: Go to Railway Dashboard > Flask Service > Variables > Add Reference Secret.")
        return False

    # 2. Log the connection attempt (Masking the password for security)
    # This helps us confirm if it's still trying to use the old 'crossover.proxy'
    connection_host = db_url.split('@')[-1] if '@' in db_url else "Unknown"
    print(f"🔄 Attempting to connect to: {connection_host}")

    # 3. Standardize the prefix (Required for some Psycopg2/SQLAlchemy versions)
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    try:
        # 4. Initialize the Threaded Pool
        # minconn=1, maxconn=20 allows the app to handle multiple users at once
        connection_pool = psycopg2.pool.ThreadedConnectionPool(
            1, 20, dsn=db_url
        )
        print("✅ DATABASE CONNECTION SUCCESS: Pool initialized.")
        return True
    except Exception as e:
        print(f"❌ DATABASE CONNECTION FAILED: {e}")
        connection_pool = None
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