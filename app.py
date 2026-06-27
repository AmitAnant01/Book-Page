from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import razorpay
import requests
import os
import json
from datetime import datetime
import uuid

app = Flask(__name__)
app.secret_key = "bookstore_secret_2024_change_this"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///bookstore.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = "static/uploads"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

# ─── Razorpay Config ─────────────────────────────────────────
# Get FREE keys from: https://dashboard.razorpay.com (Test mode)
RAZORPAY_KEY_ID     = "rzp_test_T6W8XxS1znhndM"       # ← replace
RAZORPAY_KEY_SECRET = "BVmjWJW6cfATJnkFaQJRnNl8"             # ← replace

rzp_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

db = SQLAlchemy(app)
ALLOWED = {"png", "jpg", "jpeg", "webp", "gif"}

# ─── Models ──────────────────────────────────────────────────
class Admin(db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class User(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(150), nullable=False)
    email      = db.Column(db.String(200), unique=True, nullable=False)
    password   = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Book(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    title       = db.Column(db.String(200), nullable=False)
    author      = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    price       = db.Column(db.Float, nullable=False)
    original_price = db.Column(db.Float, default=0)
    category    = db.Column(db.String(100), default="General")
    stock       = db.Column(db.Integer, default=10)
    image       = db.Column(db.String(300), default="")
    rating      = db.Column(db.Float, default=4.0)
    featured    = db.Column(db.Boolean, default=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

class StockRequest(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    book_id      = db.Column(db.Integer, db.ForeignKey("book.id"), nullable=False)
    customer_name  = db.Column(db.String(150))
    customer_email = db.Column(db.String(200))
    fulfilled    = db.Column(db.Boolean, default=False)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    book         = db.relationship("Book", backref="stock_requests")

class Order(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    order_id        = db.Column(db.String(100), unique=True)
    razorpay_order_id = db.Column(db.String(100))
    razorpay_payment_id = db.Column(db.String(100))
    customer_name   = db.Column(db.String(200))
    customer_email  = db.Column(db.String(200))
    customer_phone  = db.Column(db.String(20))
    customer_address = db.Column(db.Text)
    items_json      = db.Column(db.Text)
    total_amount    = db.Column(db.Float)
    status          = db.Column(db.String(50), default="pending")
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

# ─── Helpers ─────────────────────────────────────────────────
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated

# ─── Public Routes ───────────────────────────────────────────
@app.route("/")
@login_required
def index():
    category = request.args.get("category", "")
    search   = request.args.get("q", "")
    sort     = request.args.get("sort", "newest")

    query = Book.query
    if category:
        query = query.filter_by(category=category)
    if search:
        query = query.filter(
            (Book.title.ilike(f"%{search}%")) | (Book.author.ilike(f"%{search}%"))
        )
    if sort == "price_asc":
        query = query.order_by(Book.price.asc())
    elif sort == "price_desc":
        query = query.order_by(Book.price.desc())
    elif sort == "rating":
        query = query.order_by(Book.rating.desc())
    else:
        query = query.order_by(Book.created_at.desc())

    books      = query.all()
    featured   = Book.query.filter_by(featured=True).limit(4).all()
    categories = db.session.query(Book.category).distinct().all()
    categories = [c[0] for c in categories]
    return render_template("index.html", books=books, featured=featured,
                           categories=categories, current_cat=category,
                           search=search, sort=sort, rzp_key=RAZORPAY_KEY_ID)

@app.route("/book/<int:book_id>")
@login_required
def book_detail(book_id):
    book     = Book.query.get_or_404(book_id)
    related  = Book.query.filter_by(category=book.category).filter(Book.id != book_id).limit(4).all()
    return render_template("book_detail.html", book=book, related=related, rzp_key=RAZORPAY_KEY_ID)

@app.route("/book/<int:book_id>/notify", methods=["POST"])
@login_required
def notify_me(book_id):
    book = Book.query.get_or_404(book_id)
    user = User.query.get(session["user_id"])
    existing = StockRequest.query.filter_by(book_id=book_id, customer_email=user.email, fulfilled=False).first()
    if not existing:
        req = StockRequest(book_id=book_id, customer_name=user.name, customer_email=user.email)
        db.session.add(req)
        db.session.commit()
    return jsonify({"success": True})


@app.route("/cart/add", methods=["POST"])
def cart_add():
    data    = request.get_json()
    book_id = str(data.get("book_id"))
    qty     = int(data.get("qty", 1))
    book    = Book.query.get(book_id)
    if not book:
        return jsonify({"success": False, "msg": "Book not found"})
    cart = session.get("cart", {})
    cart[book_id] = cart.get(book_id, 0) + qty
    session["cart"] = cart
    session.modified = True
    return jsonify({"success": True, "count": sum(cart.values())})

@app.route("/cart/remove", methods=["POST"])
def cart_remove():
    data    = request.get_json()
    book_id = str(data.get("book_id"))
    cart    = session.get("cart", {})
    cart.pop(book_id, None)
    session["cart"] = cart
    session.modified = True
    return jsonify({"success": True, "count": sum(cart.values())})

@app.route("/cart/update", methods=["POST"])
def cart_update():
    data    = request.get_json()
    book_id = str(data.get("book_id"))
    qty     = int(data.get("qty", 1))
    cart    = session.get("cart", {})
    if qty <= 0:
        cart.pop(book_id, None)
    else:
        cart[book_id] = qty
    session["cart"] = cart
    session.modified = True
    total = sum(Book.query.get(int(k)).price * v for k, v in cart.items() if Book.query.get(int(k)))
    return jsonify({"success": True, "count": sum(cart.values()), "total": total})

@app.route("/cart")
@login_required
def cart_page():
    cart  = session.get("cart", {})
    items = []
    total = 0
    for book_id, qty in cart.items():
        book = Book.query.get(int(book_id))
        if book:
            items.append({"book": book, "qty": qty, "subtotal": book.price * qty})
            total += book.price * qty
    return render_template("cart.html", items=items, total=total, rzp_key=RAZORPAY_KEY_ID)

# ─── Checkout / Razorpay ─────────────────────────────────────
@app.route("/checkout", methods=["POST"])
def checkout():
    cart = session.get("cart", {})
    if not cart:
        return jsonify({"error": "Cart is empty"}), 400

    total = 0
    for book_id, qty in cart.items():
        book = Book.query.get(int(book_id))
        if book:
            total += book.price * qty

    amount_paise = int(total * 100)  # Razorpay uses paise

    rzp_order = rzp_client.order.create({
        "amount":   amount_paise,
        "currency": "INR",
        "receipt":  f"rcpt_{uuid.uuid4().hex[:8]}",
        "payment_capture": 1
    })

    # Save pending order
    items_data = []
    for book_id, qty in cart.items():
        book = Book.query.get(int(book_id))
        if book:
            items_data.append({"id": book.id, "title": book.title, "price": book.price, "qty": qty})

    order = Order(
        order_id=f"ORD-{uuid.uuid4().hex[:8].upper()}",
        razorpay_order_id=rzp_order["id"],
        items_json=json.dumps(items_data),
        total_amount=total,
        status="pending"
    )
    db.session.add(order)
    db.session.commit()

    return jsonify({
        "rzp_order_id": rzp_order["id"],
        "amount":       amount_paise,
        "currency":     "INR",
        "order_db_id":  order.id
    })

@app.route("/payment/success", methods=["POST"])
def payment_success():
    data = request.get_json()
    razorpay_order_id   = data.get("razorpay_order_id")
    razorpay_payment_id = data.get("razorpay_payment_id")
    razorpay_signature  = data.get("razorpay_signature")
    order_db_id         = data.get("order_db_id")
    customer            = data.get("customer", {})

    # Verify signature
    try:
        rzp_client.utility.verify_payment_signature({
            "razorpay_order_id":   razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature":  razorpay_signature
        })
        verified = True
    except Exception:
        verified = False

    order = Order.query.get(order_db_id)
    if order:
        order.razorpay_payment_id = razorpay_payment_id
        order.customer_name       = customer.get("name", "")
        order.customer_email      = customer.get("email", "")
        order.customer_phone      = customer.get("phone", "")
        order.customer_address    = customer.get("address", "")
        order.status              = "paid" if verified else "failed"
        db.session.commit()

        # Reduce stock
        if verified:
            items = json.loads(order.items_json)
            for item in items:
                book = Book.query.get(item["id"])
                if book and book.stock > 0:
                    book.stock = max(0, book.stock - item["qty"])
            db.session.commit()
            session.pop("cart", None)

    return jsonify({"success": verified, "order_id": order.order_id if order else ""})

@app.route("/order/confirmation/<order_id>")
def order_confirmation(order_id):
    order = Order.query.filter_by(order_id=order_id).first_or_404()
    items = json.loads(order.items_json)
    return render_template("confirmation.html", order=order, items=items)

# ─── User Auth (Signup / Login) ──────────────────────────────
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if session.get("user_id"):
        return redirect(url_for("index"))
    if request.method == "POST":
        name     = request.form.get("name", "").strip()
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm", "")

        if not name or not email or not password:
            flash("Please fill all fields", "error")
            return render_template("signup.html")
        if password != confirm:
            flash("Passwords do not match", "error")
            return render_template("signup.html")
        if User.query.filter_by(email=email).first():
            flash("An account with this email already exists", "error")
            return render_template("signup.html")

        user = User(name=name, email=email, password=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()
        session["user_id"]   = user.id
        session["user_name"] = user.name
        flash("Account created successfully! Welcome 🎉", "success")
        return redirect(url_for("index"))
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("index"))
    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user     = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            session["user_id"]   = user.id
            session["user_name"] = user.name
            flash(f"Welcome back, {user.name}! 👋", "success")
            next_url = request.args.get("next") or url_for("index")
            return redirect(next_url)
        flash("Invalid email or password", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("user_name", None)
    session.pop("cart", None)
    flash("You have been logged out", "success")
    return redirect(url_for("login"))

# ─── Free Book Search API (Open Library — no key, no quota) ──
@app.route("/api/search-books")
def api_search_books():
    q = request.args.get("q", "").strip()
    if not q or len(q) < 2:
        return jsonify({"results": []})

    results = []
    try:
        resp = requests.get(
            "https://openlibrary.org/search.json",
            params={"q": q, "limit": 6, "fields": "title,author_name,cover_i,key"},
            headers={"User-Agent": "BookPageApp/1.0"},
            timeout=8
        )
        print(f"[search-books] status={resp.status_code} for q='{q}'")
        data = resp.json()
        for doc in data.get("docs", []):
            cover_id = doc.get("cover_i")
            thumb = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else ""
            results.append({
                "title":   doc.get("title", "Untitled"),
                "authors": ", ".join(doc.get("author_name", [])) or "Unknown",
                "thumb":   thumb,
                "link":    f"https://openlibrary.org{doc.get('key', '')}"
            })
    except Exception as e:
        print(f"[search-books] ERROR: {e}")

    # Fallback: also try matching local catalog if external API gives nothing
    if not results:
        local = Book.query.filter(
            (Book.title.ilike(f"%{q}%")) | (Book.author.ilike(f"%{q}%"))
        ).limit(6).all()
        for b in local:
            results.append({
                "title":   b.title,
                "authors": b.author,
                "thumb":   f"/static/uploads/{b.image}" if b.image else "",
                "link":    url_for("book_detail", book_id=b.id)
            })

    return jsonify({"results": results})


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        admin    = Admin.query.filter_by(username=username).first()
        if admin and check_password_hash(admin.password, password):
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Invalid credentials", "error")
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))

# ─── Admin Dashboard ─────────────────────────────────────────
@app.route("/admin")
@admin_required
def admin_dashboard():
    books  = Book.query.order_by(Book.created_at.desc()).all()
    orders = Order.query.order_by(Order.created_at.desc()).limit(20).all()
    out_of_stock = Book.query.filter(Book.stock <= 0).all()
    pending_requests = StockRequest.query.filter_by(fulfilled=False).order_by(StockRequest.created_at.desc()).all()
    stats  = {
        "total_books":  Book.query.count(),
        "total_orders": Order.query.count(),
        "paid_orders":  Order.query.filter_by(status="paid").count(),
        "revenue":      db.session.query(db.func.sum(Order.total_amount)).filter_by(status="paid").scalar() or 0
    }
    return render_template("admin_dashboard.html", books=books, orders=orders, stats=stats,
                           out_of_stock=out_of_stock, pending_requests=pending_requests)

@app.route("/admin/book/add", methods=["GET", "POST"])
@admin_required
def admin_add_book():
    if request.method == "POST":
        image_filename = ""
        if "image" in request.files:
            file = request.files["image"]
            if file and file.filename and allowed_file(file.filename):
                filename       = secure_filename(file.filename)
                unique_name    = f"{uuid.uuid4().hex}_{filename}"
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], unique_name))
                image_filename = unique_name

        book = Book(
            title          = request.form.get("title"),
            author         = request.form.get("author"),
            description    = request.form.get("description", ""),
            price          = float(request.form.get("price", 0)),
            original_price = float(request.form.get("original_price", 0)),
            category       = request.form.get("category", "General"),
            stock          = int(request.form.get("stock", 10)),
            rating         = float(request.form.get("rating", 4.0)),
            featured       = bool(request.form.get("featured")),
            image          = image_filename
        )
        db.session.add(book)
        db.session.commit()
        flash("Book added successfully!", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_book_form.html", book=None, action="Add")

@app.route("/admin/book/edit/<int:book_id>", methods=["GET", "POST"])
@admin_required
def admin_edit_book(book_id):
    book = Book.query.get_or_404(book_id)
    if request.method == "POST":
        if "image" in request.files:
            file = request.files["image"]
            if file and file.filename and allowed_file(file.filename):
                filename    = secure_filename(file.filename)
                unique_name = f"{uuid.uuid4().hex}_{filename}"
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], unique_name))
                book.image  = unique_name

        book.title          = request.form.get("title")
        book.author         = request.form.get("author")
        book.description    = request.form.get("description", "")
        book.price          = float(request.form.get("price", 0))
        book.original_price = float(request.form.get("original_price", 0))
        book.category       = request.form.get("category", "General")
        book.stock          = int(request.form.get("stock", 10))
        book.rating         = float(request.form.get("rating", 4.0))
        book.featured       = bool(request.form.get("featured"))
        db.session.commit()
        flash("Book updated!", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_book_form.html", book=book, action="Edit")

@app.route("/admin/book/delete/<int:book_id>", methods=["POST"])
@admin_required
def admin_delete_book(book_id):
    book = Book.query.get_or_404(book_id)
    db.session.delete(book)
    db.session.commit()
    return jsonify({"success": True})

@app.route("/admin/book/restock/<int:book_id>", methods=["POST"])
@admin_required
def admin_restock(book_id):
    book = Book.query.get_or_404(book_id)
    data = request.get_json() or {}
    qty  = int(data.get("qty", 10))
    book.stock += qty
    db.session.commit()
    # mark pending notify requests for this book as fulfilled
    StockRequest.query.filter_by(book_id=book_id, fulfilled=False).update({"fulfilled": True})
    db.session.commit()
    return jsonify({"success": True, "new_stock": book.stock})

@app.route("/admin/orders")
@admin_required
def admin_orders():
    orders = Order.query.order_by(Order.created_at.desc()).all()
    return render_template("admin_orders.html", orders=orders)

# ─── API: cart count ─────────────────────────────────────────
@app.route("/api/cart-count")
def cart_count():
    cart = session.get("cart", {})
    return jsonify({"count": sum(cart.values())})

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        # Create default admin if not exists
        if not Admin.query.first():
            admin = Admin(
                username="admin",
                password=generate_password_hash("admin123")
            )
            db.session.add(admin)
            # Add sample books
            sample_books = [
                Book(title="The Alchemist", author="Paulo Coelho", price=299, original_price=499,
                     category="Fiction", stock=50, rating=4.8, featured=True,
                     description="A magical story about following your dreams."),
                Book(title="Atomic Habits", author="James Clear", price=349, original_price=599,
                     category="Self-Help", stock=30, rating=4.9, featured=True,
                     description="Tiny changes, remarkable results."),
                Book(title="Rich Dad Poor Dad", author="Robert Kiyosaki", price=249, original_price=399,
                     category="Finance", stock=25, rating=4.7, featured=True,
                     description="What the rich teach their kids about money."),
                Book(title="Deep Work", author="Cal Newport", price=279, original_price=450,
                     category="Self-Help", stock=20, rating=4.6, featured=False,
                     description="Rules for focused success in a distracted world."),
                Book(title="1984", author="George Orwell", price=199, original_price=299,
                     category="Fiction", stock=40, rating=4.8, featured=True,
                     description="A dystopian novel that remains deeply relevant."),
                Book(title="Python Crash Course", author="Eric Matthes", price=499, original_price=799,
                     category="Technology", stock=15, rating=4.7, featured=False,
                     description="A hands-on, project-based introduction to programming."),
            ]
            for b in sample_books:
                db.session.add(b)
            db.session.commit()
            print("✅ DB initialized. Admin: admin / admin123")
    app.run(debug=True, port=5000)
