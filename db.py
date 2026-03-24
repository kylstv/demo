import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Load local .env if it exists
load_dotenv()

def get_db():
    """Return a new PostgreSQL connection using the Railway URL."""
    # 1. Get the URL from Railway's environment variables
    db_url = os.environ.get("DATABASE_URL")

    # 2. Fix for "postgres://" vs "postgresql://"
    # Modern SQLAlchemy/psycopg2 requires 'postgresql://'
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    try:
        if db_url:
            # Connect using the full string (Production)
            return psycopg2.connect(
                db_url, 
                cursor_factory=psycopg2.extras.RealDictCursor
            )
        else:
            # Fallback for Local Development
            print("⚠️ DATABASE_URL not found, using local variables.")
            return psycopg2.connect(
                host=os.getenv("DB_HOST", "localhost"),
                port=os.getenv("DB_PORT", 5432),
                dbname=os.getenv("DB_NAME", "railway"),
                user=os.getenv("DB_USER", "postgres"),
                password=os.getenv("DB_PASSWORD", "password"),
                cursor_factory=psycopg2.extras.RealDictCursor
            )
    except psycopg2.Error as e:
        print(f"❌ DATABASE CONNECTION ERROR: {e}")
        raise e

def query(sql, params=(), fetchone=False, fetchall=False, commit=False):
    """Convenience wrapper for quick queries."""
    conn = get_db()
    try:
        # Using 'with' handles the cursor cleanup automatically
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if commit:
                conn.commit()
                return cur.rowcount
            if fetchone:
                return cur.fetchone()
            if fetchall:
                return cur.fetchall()
    except Exception as e:
        print(f"❌ QUERY ERROR: {sql}")
        print(f"Details: {e}")
        raise e
    finally:
        conn.close()