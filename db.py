import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

def get_db():
    """Return a new PostgreSQL connection."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "containers-us-west-123.railway.app"),
        port=os.getenv("DB_PORT", 5432),
        dbname=os.getenv("DB_NAME", "railway"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "dRRKqSPDPAYcvAQSLcKRWCpWeuKhmpFz"),
        cursor_factory=psycopg2.extras.RealDictCursor
    )


def query(sql, params=(), fetchone=False, fetchall=False, commit=False):
    """Convenience wrapper for quick queries."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        if commit:
            conn.commit()
            return cur.rowcount
        if fetchone:
            return cur.fetchone()
        if fetchall:
            return cur.fetchall()
    finally:
        conn.close()
