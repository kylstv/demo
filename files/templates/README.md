# MyStore — IT310 Final Project
**Web-Based Store Management System**
Stack: Python (Flask) · HTML/CSS · PostgreSQL

---

## 📁 Project Structure

```
store_project/
├── app.py                        ← Main Flask application (all routes)
├── db.py                         ← PostgreSQL connection helper
├── schema.sql                    ← Database schema + default admin seed
├── requirements.txt              ← Python dependencies
├── .env.example                  ← Environment variable template
│
├── static/
│   ├── css/style.css             ← Full custom CSS (Navy & Gold theme)
│   └── images/products/          ← Auto-created; stores watermarked product images
│
└── templates/
    ├── base.html                 ← Base layout (navbar, flash messages, footer)
    ├── login.html
    ├── register.html             ← With math CAPTCHA
    ├── forgot_password.html
    ← reset_password.html
    ├── home.html                 ← Hero, categories, featured products
    ├── products.html             ← Product grid/list, search, filter, pagination
    ├── product_detail.html       ← Single product with qty picker
    ├── cart.html
    ├── checkout.html             ← PayPal JS SDK integration
    ├── order_success.html
    ├── about.html
    └── admin/
        ├── dashboard.html        ← Chart.js graphs (sales + categories)
        ├── categories.html
        ├── products.html
        ├── product_form.html     ← Add / Edit product with image preview
        ├── users.html            ← Delete with admin password modal
        └── orders.html           ← Transaction list + PDF export button
```

---

## ⚙️ Setup Instructions

### 1. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 2. Create PostgreSQL database
```sql
CREATE DATABASE store_db;
```

### 3. Run the schema
```bash
psql -U postgres -d store_db -f schema.sql
```
This creates all tables and seeds a default **admin** account:
- Email: `admin@store.com`
- Password: `Admin@1234`

### 4. Configure environment variables
```bash
cp .env.example .env
```
Edit `.env` with your actual values:
```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=store_db
DB_USER=postgres
DB_PASSWORD=your_pg_password

SECRET_KEY=some-long-random-string

# Gmail SMTP (enable App Passwords in Google Account)
MAIL_USERNAME=your@gmail.com
MAIL_PASSWORD=your_app_password

# PayPal Developer Sandbox credentials
PAYPAL_CLIENT_ID=your_sandbox_client_id
PAYPAL_CLIENT_SECRET=your_sandbox_secret
PAYPAL_MODE=sandbox
```

### 5. Run the application
```bash
python app.py
```
Visit: **http://127.0.0.1:5000**

---

## 🔑 Default Credentials

| Role  | Email             | Password    |
|-------|-------------------|-------------|
| Admin | admin@store.com   | Admin@1234  |

---

## ✅ Feature Checklist (Rubric Coverage)

### I. Interface & Organization Design
- [x] Consistent Navy & Gold color palette throughout
- [x] Tooltips via `title` attributes, placeholder prompts on all inputs
- [x] Responsive layout (mobile-friendly grid)

### II. User Privileges
- [x] **Register** — math CAPTCHA + email verification token
- [x] **Login / Logout** — Flask `session`-based (cookie-backed)
- [x] **Forgot password** — token emailed, expires in 1 hour
- [x] **Home** — dynamic category cards + featured products
- [x] **Product List** — gallery/list toggle, category filter, tag search
- [x] **Pagination** — 6 items per page
- [x] **Cart** — add/remove items, display total
- [x] **Checkout** — PayPal JS SDK (Sandbox)

### III. Administrator Privileges
- [x] **Admin Login** — shared login route, redirects to dashboard
- [x] **Add Categories** — with description
- [x] **Upload Products** — photo, price, description, quantity, tags, category
- [x] **View Users** — table of all registered accounts
- [x] **Delete Users** — requires admin password confirmation modal
- [x] **Update Products** — edit all fields, replace image
- [x] **Delete/Add Stocks** — stock field on product form
- [x] **View Payment Transactions** — orders page with PayPal IDs + totals

### IV. Miscellaneous
- [x] **Image Watermarking** — Pillow adds "© MyStore" to all uploads
- [x] **PayPal Checkout** — JS SDK (Sandbox; switch `PAYPAL_MODE=live` for production)
- [x] **PDF Report** — ReportLab generates downloadable sales report
- [ ] **Online Hosting** — Deploy to Railway / Render / PythonAnywhere (see below)

---

## 🚀 Free Hosting Options

### Railway (recommended)
1. Push code to GitHub
2. Go to https://railway.app → New Project → Deploy from GitHub
3. Add a PostgreSQL plugin
4. Set environment variables in Railway dashboard
5. Done — Railway auto-detects Flask

### Render
1. Push to GitHub
2. https://render.com → New Web Service
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app`
5. Add PostgreSQL database + set env vars

### PythonAnywhere (free tier)
1. Upload files via Files tab
2. Create a PostgreSQL-compatible MySQL DB (or upgrade for PostgreSQL)
3. Set up WSGI config pointing to `app.py`

---

## 🔧 PayPal Setup (Sandbox)

1. Go to https://developer.paypal.com
2. Create a sandbox app → get **Client ID**
3. Paste into `.env` as `PAYPAL_CLIENT_ID`
4. Use sandbox buyer account to test payments
5. Switch `PAYPAL_MODE=live` and use live credentials for production

---

## 📧 Gmail SMTP Setup

1. Enable 2FA on your Google Account
2. Go to Google Account → Security → App Passwords
3. Generate an App Password for "Mail"
4. Use that 16-char password as `MAIL_PASSWORD` in `.env`
