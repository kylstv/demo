import os
import uuid
import bcrypt
import secrets
from datetime import datetime, timedelta
from functools import wraps
from io import BytesIO
import random

import psycopg2.extras
from dotenv import load_dotenv
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, jsonify, send_file, abort)
from flask_mail import Mail, Message
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

from db import get_db, release_db, query

load_dotenv()

# ─── App Setup ────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")
app.config["UPLOAD_FOLDER"] = os.path.join("static", "images", "products")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB

# Mail config
app.config["MAIL_SERVER"]   = os.getenv("MAIL_SERVER", "smtp.gmail.com")
app.config["MAIL_PORT"]     = int(os.getenv("MAIL_PORT", 587))
app.config["MAIL_USE_TLS"]  = os.getenv("MAIL_USE_TLS", "True") == "True"
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME", "")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD", "")
mail = Mail(app)

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

# ─── Helpers ──────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        if not session.get("is_admin"):
            abort(403)
        return f(*args, **kwargs)
    return decorated


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def add_watermark(image_path):
    """Stamp a subtle watermark on the product image."""
    try:
        img  = Image.open(image_path).convert("RGBA")
        txt  = Image.new("RGBA", img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(txt)
        w, h = img.size
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                max(16, h // 20),
            )
        except Exception:
            font = ImageFont.load_default()
        text = "© MyStore"
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((w - tw) / 2, h - th - 10), text, font=font,
                  fill=(255, 255, 255, 120))
        watermarked = Image.alpha_composite(img, txt).convert("RGB")
        watermarked.save(image_path, "JPEG", quality=90)
    except Exception as e:
        app.logger.warning(f"Watermark failed: {e}")


def save_product_image(file):
    """Validate, resize, watermark and save an uploaded image.
    Returns the relative URL path or raises ValueError on bad input."""
    if not allowed_file(file.filename):
        raise ValueError("Invalid file type. Allowed: jpg, jpeg, png, webp")
    filename  = f"{uuid.uuid4().hex}.jpg"
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    img = Image.open(file).convert("RGB")
    img.thumbnail((800, 800))
    img.save(save_path, "JPEG", quality=88)
    add_watermark(save_path)
    return os.path.join("images", "products", filename).replace("\\", "/")


def send_verification_email(user_email, token):
    try:
        link = url_for("verify_email", token=token, _external=True)
        msg  = Message(
            "Verify your MyStore account",
            sender=app.config["MAIL_USERNAME"],
            recipients=[user_email],
        )
        msg.body = (
            f"Click to verify your account:\n{link}\n\n"
            "Link expires in 24 hours."
        )
        mail.send(msg)
    except Exception as e:
        app.logger.error(f"Mail send failed: {e}")


def send_reset_email(user_email, token):
    try:
        link = url_for("reset_password", token=token, _external=True)
        msg  = Message(
            "Reset your MyStore password",
            sender=app.config["MAIL_USERNAME"],
            recipients=[user_email],
        )
        msg.body = (
            f"Click to reset your password:\n{link}\n\n"
            "Link expires in 1 hour."
        )
        mail.send(msg)
    except Exception as e:
        app.logger.error(f"Mail send failed: {e}")


def _cart_items_and_total(cart: dict, cur) -> tuple[list, float]:
    """Shared helper: given a cart dict and an open cursor, return
    (items_list, total).  Items that no longer exist are silently skipped."""
    if not cart:
        return [], 0.0
    ids = [int(k) for k in cart if str(k).isdigit()]
    if not ids:
        return [], 0.0
    cur.execute("SELECT * FROM products WHERE id = ANY(%s)", (ids,))
    items, total = [], 0.0
    for p in cur.fetchall():
        qty      = cart[str(p["id"])]
        subtotal = float(p["price"]) * qty
        total   += subtotal
        items.append({**p, "qty": qty, "subtotal": subtotal})
    return items, round(total, 2)

# ─── Auth Routes ──────────────────────────────────────────────────────────────

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        email    = request.form["email"].strip().lower()
        password = request.form["password"]
        captcha  = request.form.get("captcha", "")
        expected = session.get("captcha_answer")

        if str(captcha) != str(expected):
            flash("CAPTCHA incorrect. Try again.", "danger")
            return redirect(url_for("register"))

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return redirect(url_for("register"))

        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        token  = secrets.token_urlsafe(32)
        conn   = get_db()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users (username, email, password, verify_token) "
                "VALUES (%s,%s,%s,%s)",
                (username, email, hashed, token),
            )
            conn.commit()
            send_verification_email(email, token)
            flash(
                "Registration successful! Check your email to verify your account.",
                "success",
            )
            return redirect(url_for("login"))
        except Exception:
            conn.rollback()
            flash("Username or email already taken.", "danger")
        finally:
            release_db(conn)

    a, b = random.randint(1, 9), random.randint(1, 9)
    session["captcha_answer"] = a + b
    return render_template("register.html", captcha_question=f"{a} + {b} = ?")


@app.route("/verify/<token>")
def verify_email(token):
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT id FROM users WHERE verify_token=%s", (token,))
        user = cur.fetchone()
        if not user:
            flash("Invalid or expired verification link.", "danger")
            return redirect(url_for("login"))
        cur.execute(
            "UPDATE users SET is_verified=TRUE, verify_token=NULL WHERE id=%s",
            (user["id"],),
        )
        conn.commit()
        flash("Email verified! You can now log in.", "success")
    finally:
        release_db(conn)
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email    = request.form["email"].strip().lower()
        password = request.form["password"]
        conn = get_db()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT * FROM users WHERE email=%s", (email,))
            user = cur.fetchone()
        finally:
            release_db(conn)

        if user and bcrypt.checkpw(password.encode(), user["password"].encode()):
            if not user["is_verified"] and not user["is_admin"]:
                flash("Please verify your email first.", "warning")
                return redirect(url_for("login"))
            session["user_id"]  = user["id"]
            session["username"] = user["username"]
            session["is_admin"] = user["is_admin"]
            session.setdefault("cart", {})
            flash(f"Welcome back, {user['username']}!", "success")
            return redirect(
                url_for("admin_dashboard") if user["is_admin"] else url_for("home")
            )
        flash("Invalid email or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email   = request.form["email"].strip().lower()
        token   = secrets.token_urlsafe(32)
        expires = datetime.now() + timedelta(hours=1)
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE users SET reset_token=%s, reset_expires=%s WHERE email=%s",
                (token, expires, email),
            )
            conn.commit()
            if cur.rowcount:
                send_reset_email(email, token)
        finally:
            release_db(conn)
        # Always show the same message to prevent user enumeration
        flash("If that email exists, a reset link has been sent.", "info")
        return redirect(url_for("login"))
    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT * FROM users WHERE reset_token=%s AND reset_expires > NOW()",
            (token,),
        )
        user = cur.fetchone()
        if not user:
            flash("Invalid or expired reset link.", "danger")
            return redirect(url_for("login"))
        if request.method == "POST":
            new_pw = request.form["password"]
            if len(new_pw) < 8:
                flash("Password must be at least 8 characters.", "danger")
                return render_template("reset_password.html", token=token)
            hashed = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt()).decode()
            cur.execute(
                "UPDATE users SET password=%s, reset_token=NULL, "
                "reset_expires=NULL WHERE id=%s",
                (hashed, user["id"]),
            )
            conn.commit()
            flash("Password reset successful! Please log in.", "success")
            return redirect(url_for("login"))
    finally:
        release_db(conn)
    return render_template("reset_password.html", token=token)

# ─── Public / User Routes ─────────────────────────────────────────────────────

@app.route("/")
def home():
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM categories ORDER BY name")
        categories = cur.fetchall()
        cur.execute("""
            SELECT p.*, c.name AS category_name
            FROM products p LEFT JOIN categories c ON p.category_id = c.id
            ORDER BY p.created_at DESC LIMIT 8
        """)
        featured = cur.fetchall()
    finally:
        release_db(conn)
    return render_template("home.html", categories=categories, featured=featured)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/products")
def products():
    cat_id   = request.args.get("category", type=int)
    search   = request.args.get("q", "").strip()
    page     = max(1, request.args.get("page", 1, type=int))  # prevent page < 1
    per_page = 6
    offset   = (page - 1) * per_page

    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM categories ORDER BY name")
        categories = cur.fetchall()

        # Build filter clauses with parameterised values only — no string interpolation
        filters, params = [], []
        if cat_id:
            filters.append("p.category_id = %s")
            params.append(cat_id)
        if search:
            filters.append(
                "(p.name ILIKE %s OR p.tags ILIKE %s OR p.description ILIKE %s)"
            )
            like = f"%{search}%"
            params.extend([like, like, like])

        where = ("WHERE " + " AND ".join(filters)) if filters else ""

        # Use psycopg2's mogrify-safe approach: pass params as a list,
        # never format the WHERE clause itself from user input
        cur.execute(
            f"""
            SELECT p.*, c.name AS category_name
            FROM products p LEFT JOIN categories c ON p.category_id = c.id
            {where}
            ORDER BY p.created_at DESC
            LIMIT %s OFFSET %s
            """,
            params + [per_page, offset],
        )
        prods = cur.fetchall()

        cur.execute(
            f"SELECT COUNT(*) AS total FROM products p {where}", params
        )
        total = cur.fetchone()["total"]
    finally:
        release_db(conn)

    total_pages = max(1, (total + per_page - 1) // per_page)
    return render_template(
        "products.html",
        products=prods,
        categories=categories,
        selected_cat=cat_id,
        search=search,
        page=page,
        total_pages=total_pages,
    )


@app.route("/product/<int:pid>")
def product_detail(pid):
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT p.*, c.name AS category_name
            FROM products p LEFT JOIN categories c ON p.category_id = c.id
            WHERE p.id = %s
        """, (pid,))
        product = cur.fetchone()
    finally:
        release_db(conn)
    if not product:
        abort(404)
    return render_template("product_detail.html", product=product)

# ─── Cart ─────────────────────────────────────────────────────────────────────

@app.route("/cart")
@login_required
def cart():
    cart = session.get("cart", {})
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        items, total = _cart_items_and_total(cart, cur)
    finally:
        release_db(conn)
    return render_template("cart.html", items=items, total=total)


@app.route("/cart/add/<int:pid>", methods=["POST"])
@login_required
def cart_add(pid):
    try:
        qty = int(request.form.get("qty", 1))
    except (TypeError, ValueError):
        qty = 1

    if qty < 1:
        flash("Quantity must be at least 1.", "warning")
        return redirect(request.referrer or url_for("products"))

    # Verify product exists before adding
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT id, stock FROM products WHERE id=%s", (pid,))
        product = cur.fetchone()
    finally:
        release_db(conn)

    if not product:
        flash("Product not found.", "danger")
        return redirect(request.referrer or url_for("products"))

    cart     = session.get("cart", {})
    new_qty  = cart.get(str(pid), 0) + qty

    # Soft-cap at available stock
    if product["stock"] is not None and new_qty > product["stock"]:
        new_qty = product["stock"]
        flash(f"Only {product['stock']} in stock — cart updated to maximum.", "warning")
    else:
        flash("Added to cart!", "success")

    cart[str(pid)]   = new_qty
    session["cart"]  = cart
    session.modified = True
    return redirect(request.referrer or url_for("products"))


@app.route("/cart/remove/<int:pid>")
@login_required
def cart_remove(pid):
    cart = session.get("cart", {})
    cart.pop(str(pid), None)
    session["cart"]  = cart
    session.modified = True
    flash("Item removed from cart.", "info")
    return redirect(url_for("cart"))

# ─── Checkout ────────────────────────────────────────────────────────────────

@app.route("/checkout")
@login_required
def checkout():
    cart = session.get("cart", {})
    if not cart:
        flash("Your cart is empty.", "warning")
        return redirect(url_for("products"))
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        items, total = _cart_items_and_total(cart, cur)
    finally:
        release_db(conn)
    if not items:
        flash("Your cart is empty.", "warning")
        return redirect(url_for("products"))
    # No PayPal — nothing extra needed in the template context
    return render_template("checkout.html", items=items, total=total)


@app.route("/checkout/capture", methods=["POST"])
@login_required
def checkout_capture():
    data = request.get_json(silent=True) or {}
    cart = session.get("cart", {})

    if not cart:
        return jsonify({"error": "Cart is empty"}), 400

    # Accept both mock and (future) real order IDs gracefully
    mock_order_id = data.get("orderID", f"MOCK-{secrets.token_hex(8)}")

    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        items, total = _cart_items_and_total(cart, cur)

        if not items:
            return jsonify({"error": "No valid products in cart"}), 400

        # ── Stock check before committing anything ────────────────────────
        for item in items:
            if item["stock"] is not None and item["qty"] > item["stock"]:
                return jsonify({
                    "error": f"'{item['name']}' only has {item['stock']} units left."
                }), 409

        # ── Insert order ──────────────────────────────────────────────────
        cur.execute(
            "INSERT INTO orders (user_id, total_amount, status, mock_order_id) "
            "VALUES (%s, %s, 'paid', %s) RETURNING id",
            (session["user_id"], total, mock_order_id),
        )
        order_id = cur.fetchone()["id"]

        # ── Insert line items & decrement stock atomically ────────────────
        for item in items:
            cur.execute(
                "INSERT INTO order_items (order_id, product_id, quantity, unit_price) "
                "VALUES (%s, %s, %s, %s)",
                (order_id, item["id"], item["qty"], item["price"]),
            )
            cur.execute(
                "UPDATE products SET stock = stock - %s WHERE id = %s AND stock >= %s",
                (item["qty"], item["id"], item["qty"]),
            )
            if cur.rowcount == 0:
                # Another request depleted stock between our check and update
                raise RuntimeError(
                    f"Stock conflict on '{item['name']}' — please retry."
                )

        conn.commit()
        session.pop("cart", None)
        return jsonify({"success": True, "order_id": order_id})

    except RuntimeError as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 409
    except Exception as e:
        conn.rollback()
        app.logger.error(f"Checkout capture error: {e}")
        return jsonify({"error": "An unexpected error occurred."}), 500
    finally:
        release_db(conn)


@app.route("/order/<int:oid>/success")
@login_required
def order_success(oid):
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT * FROM orders WHERE id=%s AND user_id=%s",
            (oid, session["user_id"]),
        )
        order = cur.fetchone()
        if not order:
            abort(404)
        cur.execute("""
            SELECT oi.*, p.name, p.image_path
            FROM order_items oi JOIN products p ON oi.product_id = p.id
            WHERE oi.order_id = %s
        """, (oid,))
        items = cur.fetchall()
    finally:
        release_db(conn)
    return render_template("order_success.html", order=order, items=items)

# ─── Admin Routes ─────────────────────────────────────────────────────────────

@app.route("/admin")
@admin_required
def admin_dashboard():
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT COUNT(*) AS c FROM users WHERE is_admin=FALSE")
        total_users    = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM products")
        total_products = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM orders WHERE status='paid'")
        total_orders   = cur.fetchone()["c"]
        cur.execute(
            "SELECT COALESCE(SUM(total_amount),0) AS rev FROM orders WHERE status='paid'"
        )
        revenue = cur.fetchone()["rev"]
        cur.execute("""
            SELECT DATE(created_at) AS day, SUM(total_amount) AS daily
            FROM orders WHERE status='paid'
            GROUP BY day ORDER BY day DESC LIMIT 7
        """)
        sales_data = cur.fetchall()
        cur.execute("""
            SELECT c.name, COUNT(p.id) AS cnt
            FROM categories c LEFT JOIN products p ON p.category_id = c.id
            GROUP BY c.name
        """)
        cat_data = cur.fetchall()
    finally:
        release_db(conn)
    return render_template(
        "admin/dashboard.html",
        total_users=total_users,
        total_products=total_products,
        total_orders=total_orders,
        revenue=revenue,
        sales_data=list(sales_data),
        cat_data=list(cat_data),
    )


@app.route("/admin/categories", methods=["GET", "POST"])
@admin_required
def admin_categories():
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if request.method == "POST":
            name = request.form["name"].strip()
            desc = request.form.get("description", "").strip()
            try:
                cur.execute(
                    "INSERT INTO categories (name, description) VALUES (%s,%s)",
                    (name, desc),
                )
                conn.commit()
                flash("Category added.", "success")
            except Exception:
                conn.rollback()
                flash("Category already exists.", "danger")
            return redirect(url_for("admin_categories"))
        cur.execute("SELECT * FROM categories ORDER BY name")
        cats = cur.fetchall()
    finally:
        release_db(conn)
    return render_template("admin/categories.html", categories=cats)


@app.route("/admin/categories/delete/<int:cid>", methods=["POST"])
@admin_required
def admin_category_delete(cid):
    query("DELETE FROM categories WHERE id=%s", (cid,), commit=True)
    flash("Category deleted.", "info")
    return redirect(url_for("admin_categories"))


@app.route("/admin/products")
@admin_required
def admin_products():
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT p.*, c.name AS category_name
            FROM products p LEFT JOIN categories c ON p.category_id = c.id
            ORDER BY p.created_at DESC
        """)
        prods = cur.fetchall()
    finally:
        release_db(conn)
    return render_template("admin/products.html", products=prods)


@app.route("/admin/products/add", methods=["GET", "POST"])
@admin_required
def admin_product_add():
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM categories ORDER BY name")
        cats = cur.fetchall()
        if request.method == "POST":
            name   = request.form["name"].strip()
            desc   = request.form.get("description", "").strip()
            price  = float(request.form["price"])
            stock  = int(request.form["stock"])
            cat_id = request.form.get("category_id") or None
            tags   = request.form.get("tags", "").strip()

            img_path = None
            file = request.files.get("image")
            if file and file.filename:
                try:
                    img_path = save_product_image(file)
                except ValueError as e:
                    flash(str(e), "danger")
                    return render_template(
                        "admin/product_form.html", categories=cats, product=None
                    )

            cur.execute("""
                INSERT INTO products
                    (name, description, price, stock, category_id, tags, image_path)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (name, desc, price, stock, cat_id, tags, img_path))
            conn.commit()
            flash("Product added!", "success")
            return redirect(url_for("admin_products"))
    finally:
        release_db(conn)
    return render_template("admin/product_form.html", categories=cats, product=None)


@app.route("/admin/products/edit/<int:pid>", methods=["GET", "POST"])
@admin_required
def admin_product_edit(pid):
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM products WHERE id=%s", (pid,))
        product = cur.fetchone()
        if not product:
            abort(404)
        cur.execute("SELECT * FROM categories ORDER BY name")
        cats = cur.fetchall()
        if request.method == "POST":
            name   = request.form["name"].strip()
            desc   = request.form.get("description", "").strip()
            price  = float(request.form["price"])
            stock  = int(request.form["stock"])
            cat_id = request.form.get("category_id") or None
            tags   = request.form.get("tags", "").strip()

            img_path = product["image_path"]
            file = request.files.get("image")
            if file and file.filename:
                try:
                    img_path = save_product_image(file)
                except ValueError as e:
                    flash(str(e), "danger")
                    return render_template(
                        "admin/product_form.html", categories=cats, product=product
                    )

            cur.execute("""
                UPDATE products
                SET name=%s, description=%s, price=%s, stock=%s,
                    category_id=%s, tags=%s, image_path=%s, updated_at=NOW()
                WHERE id=%s
            """, (name, desc, price, stock, cat_id, tags, img_path, pid))
            conn.commit()
            flash("Product updated!", "success")
            return redirect(url_for("admin_products"))
    finally:
        release_db(conn)
    return render_template("admin/product_form.html", categories=cats, product=product)


@app.route("/admin/products/delete/<int:pid>", methods=["POST"])
@admin_required
def admin_product_delete(pid):
    query("DELETE FROM products WHERE id=%s", (pid,), commit=True)
    flash("Product deleted.", "info")
    return redirect(url_for("admin_products"))


@app.route("/admin/users")
@admin_required
def admin_users():
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT id, username, email, is_admin, is_verified, created_at "
            "FROM users ORDER BY created_at DESC"
        )
        users = cur.fetchall()
    finally:
        release_db(conn)
    return render_template("admin/users.html", users=users)


@app.route("/admin/users/delete/<int:uid>", methods=["POST"])
@admin_required
def admin_user_delete(uid):
    password = request.form.get("confirm_password", "")
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT password FROM users WHERE id=%s", (session["user_id"],)
        )
        admin = cur.fetchone()
        if not admin or not bcrypt.checkpw(
            password.encode(), admin["password"].encode()
        ):
            flash("Incorrect admin password.", "danger")
            return redirect(url_for("admin_users"))
        if uid == session["user_id"]:
            flash("You cannot delete yourself.", "danger")
            return redirect(url_for("admin_users"))
        cur.execute("DELETE FROM users WHERE id=%s", (uid,))
        conn.commit()
        flash("User deleted.", "info")
    finally:
        release_db(conn)
    return redirect(url_for("admin_users"))


@app.route("/admin/orders")
@admin_required
def admin_orders():
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT o.*, u.username, u.email
            FROM orders o JOIN users u ON o.user_id = u.id
            ORDER BY o.created_at DESC
        """)
        orders = cur.fetchall()
    finally:
        release_db(conn)
    return render_template("admin/orders.html", orders=orders)


@app.route("/admin/report/pdf")
@admin_required
def admin_report_pdf():
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # mock_order_id replaces paypal_order_id
        cur.execute("""
            SELECT o.id, u.username, u.email,
                   o.total_amount, o.status,
                   o.mock_order_id, o.created_at
            FROM orders o JOIN users u ON o.user_id = u.id
            ORDER BY o.created_at DESC
        """)
        orders = cur.fetchall()
        cur.execute(
            "SELECT COALESCE(SUM(total_amount),0) AS total "
            "FROM orders WHERE status='paid'"
        )
        grand_total = cur.fetchone()["total"]
    finally:
        release_db(conn)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=30, leftMargin=30, topMargin=40, bottomMargin=30,
    )
    styles   = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("MyStore — Sales Report", styles["Title"]))
    elements.append(Paragraph(
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        styles["Normal"],
    ))
    elements.append(Spacer(1, 20))

    data = [["Order ID", "Customer", "Email", "Amount (₱)", "Status", "Date"]]
    for o in orders:
        data.append([
            str(o["id"]),
            o["username"],
            o["email"],
            f"₱{o['total_amount']:,.2f}",
            o["status"].upper(),
            o["created_at"].strftime("%Y-%m-%d"),
        ])
    data.append(["", "", "TOTAL", f"₱{grand_total:,.2f}", "", ""])

    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0),  (-1, 0),  colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR",      (0, 0),  (-1, 0),  colors.white),
        ("FONTNAME",       (0, 0),  (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0),  (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1),  (-1, -2), [colors.white, colors.HexColor("#f5f5f5")]),
        ("BACKGROUND",     (0, -1), (-1, -1), colors.HexColor("#e8f5e9")),
        ("FONTNAME",       (0, -1), (-1, -1), "Helvetica-Bold"),
        ("GRID",           (0, 0),  (-1, -1), 0.3, colors.grey),
        ("ALIGN",          (3, 0),  (3, -1),  "RIGHT"),
    ]))
    elements.append(t)
    doc.build(elements)

    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"sales_report_{datetime.now().strftime('%Y%m%d')}.pdf",
        mimetype="application/pdf",
    )

# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)