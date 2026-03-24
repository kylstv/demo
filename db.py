import os
import psycopg2
import psycopg2.extras

def get_db():
    # Railway automatically provides this "DATABASE_URL" 
    # It contains the host, port, user, and password in one string.
    url = os.environ.get('DATABASE_URL')
    
    return psycopg2.connect(
        url, 
        cursor_factory=psycopg2.extras.RealDictCursor
    )

def query(sql, params=(), fetchone=False, fetchall=False, commit=False):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if commit:
                conn.commit()
                return cur.rowcount
            if fetchone: return cur.fetchone()
            if fetchall: return cur.fetchall()
    finally:
        conn.close()