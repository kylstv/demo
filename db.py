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
        connection_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=20,
            dsn=db_url,
            sslmode="require",
            connect_timeout=10
        )
        print("✅ SUCCESS: Connected to Railway PostgreSQL!")

        # Create all tables on startup
        create_tables()
        return True

    except Exception as e:
        print(f"❌ CONNECTION FAILED: {e}")
        return False


def create_tables():
    """Creates all tables and default data if they don't exist yet."""
    conn = None
    try:
        conn = connection_pool.getconn()
        with conn.cursor() as cur:

            # Enable pgcrypto extension
            cur.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')

            # ── 1. users (no foreign key dependencies)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id            SERIAL PRIMARY KEY,
                    username      VARCHAR(80)  UNIQUE NOT NULL,
                    email         VARCHAR(150) UNIQUE NOT NULL,
                    password      TEXT NOT NULL,
                    is_admin      BOOLEAN DEFAULT FALSE,
                    is_verified   BOOLEAN DEFAULT FALSE,
                    verify_token  TEXT,
                    reset_token   TEXT,
                    reset_expires TIMESTAMP,
                    created_at    TIMESTAMP DEFAULT NOW()
                );
            """)
            print("✅ users ready")

            # ── 2. categories (no foreign key dependencies)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    id          SERIAL PRIMARY KEY,
                    name        VARCHAR(100) UNIQUE NOT NULL,
                    description TEXT,
                    created_at  TIMESTAMP DEFAULT NOW()
                );
            """)
            print("✅ categories ready")

            # ── 3. products (depends on categories)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id          SERIAL PRIMARY KEY,
                    category_id INT REFERENCES categories(id) ON DELETE SET NULL,
                    name        VARCHAR(200) NOT NULL,
                    description TEXT,
                    price       NUMERIC(10,2) NOT NULL,
                    stock       INT DEFAULT 0,
                    image_path  TEXT,
                    tags        TEXT,
                    created_at  TIMESTAMP DEFAULT NOW(),
                    updated_at  TIMESTAMP DEFAULT NOW()
                );
            """)
            print("✅ products ready")

            # ── 4. orders (depends on users)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id              SERIAL PRIMARY KEY,
                    user_id         INT REFERENCES users(id) ON DELETE CASCADE,
                    total_amount    NUMERIC(10,2) NOT NULL,
                    status          VARCHAR(50) DEFAULT 'pending',
                    paypal_order_id TEXT,
                    created_at      TIMESTAMP DEFAULT NOW()
                );
            """)
            print("✅ orders ready")

            # ── 5. order_items (depends on orders + products)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS order_items (
                    id         SERIAL PRIMARY KEY,
                    order_id   INT REFERENCES orders(id) ON DELETE CASCADE,
                    product_id INT REFERENCES products(id) ON DELETE SET NULL,
                    quantity   INT NOT NULL,
                    unit_price NUMERIC(10,2) NOT NULL
                );
            """)
            print("✅ order_items ready")

            # ── Default admin account (password: Admin@1234)
            cur.execute("""
                INSERT INTO users (username, email, password, is_admin, is_verified)
                VALUES (
                    'admin',
                    'admin@store.com',
                    '$2b$12$KiWjOEbBvAn1Rm5bE1UiA.tE0qBBW8t3.5vl8Fz7XrQ7oZ3KLQS9e',
                    TRUE,
                    TRUE
                ) ON CONFLICT DO NOTHING;
            """)
            print("✅ admin account ready")

        conn.commit()
        print("✅ All tables created/verified successfully")

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ create_tables FAILED: {e}")
        raise e

    finally:
        if conn:
            connection_pool.putconn(conn)


def get_db():
    global connection_pool

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
    """Gracefully close all connections on shutdown."""
    global connection_pool

    if connection_pool:
        connection_pool.closeall()
        print("🔒 All DB connections closed.")