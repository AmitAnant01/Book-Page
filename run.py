#!/usr/bin/env python3
"""
Book Page — Advanced Bookstore with Razorpay Payments
Run: python run.py
"""
import json
from app import app

# Register Jinja filter for admin orders page
@app.template_filter('from_json')
def from_json_filter(s):
    try:
        return json.loads(s)
    except:
        return []

if __name__ == "__main__":
    import os
    os.makedirs("static/uploads", exist_ok=True)
    print("🚀 Book Page running at http://localhost:5000")
    print("👤 Admin: http://localhost:5000/admin  (admin / admin123)")
    print("💳 Add Razorpay keys in app.py lines 15-16")
    app.run(debug=True, port=5000)
