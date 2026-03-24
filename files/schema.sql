-- ============================================================
-- IT310 Final Project - PostgreSQL Schema
-- Run: psql -U postgres -d store_db -f schema.sql
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id          SERIAL PRIMARY KEY,
    username    VARCHAR(80)  UNIQUE NOT NULL,
    email       VARCHAR(150) UNIQUE NOT NULL,
    password    TEXT NOT NULL,                   -- bcrypt hash
    is_admin    BOOLEAN DEFAULT FALSE,
    is_verified BOOLEAN DEFAULT FALSE,
    verify_token TEXT,
    reset_token  TEXT,
    reset_expires TIMESTAMP,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- Categories table
CREATE TABLE IF NOT EXISTS categories (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- Products table
CREATE TABLE IF NOT EXISTS products (
    id           SERIAL PRIMARY KEY,
    category_id  INT REFERENCES categories(id) ON DELETE SET NULL,
    name         VARCHAR(200) NOT NULL,
    description  TEXT,
    price        NUMERIC(10,2) NOT NULL,
    stock        INT DEFAULT 0,
    image_path   TEXT,
    tags         TEXT,                           -- comma-separated tags
    created_at   TIMESTAMP DEFAULT NOW(),
    updated_at   TIMESTAMP DEFAULT NOW()
);

-- Orders table
CREATE TABLE IF NOT EXISTS orders (
    id              SERIAL PRIMARY KEY,
    user_id         INT REFERENCES users(id) ON DELETE CASCADE,
    total_amount    NUMERIC(10,2) NOT NULL,
    status          VARCHAR(50) DEFAULT 'pending',   -- pending, paid, cancelled
    paypal_order_id TEXT,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Order items table
CREATE TABLE IF NOT EXISTS order_items (
    id          SERIAL PRIMARY KEY,
    order_id    INT REFERENCES orders(id) ON DELETE CASCADE,
    product_id  INT REFERENCES products(id) ON DELETE SET NULL,
    quantity    INT NOT NULL,
    unit_price  NUMERIC(10,2) NOT NULL
);

-- ============================================================
-- Default admin account  (password: Admin@1234)
-- ============================================================
INSERT INTO users (username, email, password, is_admin, is_verified)
VALUES (
    'admin',
    'admin@store.com',
    '$2b$12$KiWjOEbBvAn1Rm5bE1UiA.tE0qBBW8t3.5vl8Fz7XrQ7oZ3KLQS9e',
    TRUE,
    TRUE
) ON CONFLICT DO NOTHING;
