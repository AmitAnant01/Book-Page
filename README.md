# 📚 Book Page — Advanced Bookstore

Full-stack bookstore with:
- Browse, search, filter books
- Add to cart, quantity management
- **Real Razorpay payment** (UPI, Cards, NetBanking, Wallets)
- Admin dashboard (add/edit/delete books, view orders)
- Image upload for book covers
- Order confirmation page
- Revenue stats

---

## ⚡ Quick Start (3 steps)

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Add Razorpay Keys (FREE test mode)
1. Sign up at https://dashboard.razorpay.com (free)
2. Go to Settings → API Keys → Generate Test Key
3. Open `app.py` and replace lines 15–16:
```python
RAZORPAY_KEY_ID     = "rzp_test_XXXXXXXXXXXXXXXX"
RAZORPAY_KEY_SECRET = "XXXXXXXXXXXXXXXXXXXXXXXX"
```

### 3. Run
```bash
python run.py
```

Visit: http://localhost:5000  
Admin: http://localhost:5000/admin → `admin` / `admin123`

---

## 🔑 Features

| Feature | Details |
|---|---|
| Shop | Browse, search, filter by category, sort by price/rating |
| Cart | Add/remove, qty update, subtotal calculation |
| Payment | Razorpay — UPI, Debit/Credit Card, NetBanking, Wallets |
| Admin | Add/Edit/Delete books with image upload |
| Orders | Full order history with customer details |
| Stock | Auto-deducts on successful payment |

## 💳 Test Payment Cards
Use these in test mode:
- **Card**: 4111 1111 1111 1111 | Expiry: any future | CVV: any
- **UPI**: success@razorpay

## 🔐 Change Admin Password
In `app.py`, `__main__` block, change `"admin123"` to your password.
