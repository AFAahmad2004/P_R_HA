from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import bcrypt
import jwt
import datetime
import os
import base64
from functools import wraps

app = Flask(__name__)
CORS(app)

SECRET_KEY = "your_secret_key_change_this_in_production"
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization")
        if not token:
            return jsonify({"error": "Token missing"}), 401
        try:
            token = token.replace("Bearer ", "")
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            request.user = data
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    @token_required
    def decorated(*args, **kwargs):
        if request.user.get("role") != "admin":
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated


@app.route("/")
def home():
    return "Server is running"


@app.route('/register', methods=['POST'])
def register():
    data = request.json
    if not data.get('name') or not data.get('email') or not data.get('password'):
        return jsonify({"error": "All fields are required"}), 400
    hashed_pw = bcrypt.hashpw(data['password'].encode('utf-8'), bcrypt.gensalt())
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO users(name, email, password, role) VALUES (?,?,?,?)",
                (data['name'], data['email'], hashed_pw.decode('utf-8'), 'client')
            )
            conn.commit()
            user = conn.execute("SELECT * FROM users WHERE email=?", (data['email'],)).fetchone()
        token = jwt.encode({
            "id": user["id"], "role": user["role"],
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, SECRET_KEY, algorithm="HS256")
        return jsonify({"token": token, "role": user["role"], "name": user["name"]}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Email already exists"}), 409


@app.route('/login', methods=['POST'])
def login():
    data = request.json
    if not data.get('email') or not data.get('password'):
        return jsonify({"error": "Email and password required"}), 400
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE email=?", (data['email'],)).fetchone()
    if user and bcrypt.checkpw(data['password'].encode('utf-8'), user['password'].encode('utf-8')):
        token = jwt.encode({
            "id": user["id"], "role": user["role"],
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, SECRET_KEY, algorithm="HS256")
        return jsonify({"token": token, "role": user["role"], "name": user["name"]})
    return jsonify({"error": "Wrong email or password"}), 401


@app.route('/add_product', methods=['POST'])
@admin_required
def add_product():
    data = request.json
    for field in ['name', 'price', 'description', 'category']:
        if not data.get(field):
            return jsonify({"error": f"Field '{field}' is required"}), 400
    image_path = None
    if data.get('image'):
        try:
            image_data = data['image']
            if ',' in image_data:
                image_data = image_data.split(',')[1]
            ext = 'jpg'
            header = data.get('image', '')[:30]
            if 'png' in header: ext = 'png'
            elif 'webp' in header: ext = 'webp'
            filename = f"product_{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}.{ext}"
            with open(os.path.join(UPLOAD_FOLDER, filename), 'wb') as f:
                f.write(base64.b64decode(image_data))
            image_path = filename
        except Exception as e:
            return jsonify({"error": f"Image error: {str(e)}"}), 400
    show_home = 1 if data.get('show_home') else 0
    with get_db() as conn:
        conn.execute(
            "INSERT INTO products(name, price, description, category, image, show_home, date) VALUES (?,?,?,?,?,?,datetime('now'))",
            (data['name'], data['price'], data['description'], data['category'], image_path, show_home)
        )
        conn.commit()
    return jsonify({"message": "Product added successfully"}), 201


@app.route('/products')
def get_products():
    category = request.args.get('category')
    home_only = request.args.get('home')
    query = "SELECT * FROM products WHERE 1=1"
    params = []
    if category:
        query += " AND category=?"
        params.append(category)
    if home_only:
        query += " AND show_home=1"
    query += " ORDER BY id DESC"
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    result = []
    for r in rows:
        item = dict(r)
        item['image_url'] = f"http://127.0.0.1:5000/uploads/{item['image']}" if item['image'] else None
        result.append(item)
    return jsonify(result)


@app.route('/delete_product/<int:product_id>', methods=['DELETE'])
@admin_required
def delete_product(product_id):
    with get_db() as conn:
        product = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if product and product['image']:
            try: os.remove(os.path.join(UPLOAD_FOLDER, product['image']))
            except: pass
        conn.execute("DELETE FROM products WHERE id=?", (product_id,))
        conn.commit()
    return jsonify({"message": "Product deleted"})


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route('/add_update', methods=['POST'])
@admin_required
def add_update():
    data = request.json
    if not data.get('title') or not data.get('content'):
        return jsonify({"error": "Title and content are required"}), 400
    with get_db() as conn:
        conn.execute("INSERT INTO updates(title, content, date) VALUES (?,?,datetime('now'))", (data['title'], data['content']))
        conn.commit()
    return jsonify({"message": "Update added successfully"}), 201


@app.route('/delete_update/<int:update_id>', methods=['DELETE'])
@admin_required
def delete_update(update_id):
    with get_db() as conn:
        conn.execute("DELETE FROM updates WHERE id=?", (update_id,))
        conn.commit()
    return jsonify({"message": "Update deleted"})


@app.route('/updates')
def updates():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM updates ORDER BY id DESC").fetchall()
    return jsonify([dict(u) for u in rows])


@app.route('/contact', methods=['POST'])
def contact():
    data = request.json
    if not data.get('name') or not data.get('email') or not data.get('message'):
        return jsonify({"error": "All fields required"}), 400
    with get_db() as conn:
        conn.execute("INSERT INTO contacts(name, email, message, date) VALUES (?,?,?,datetime('now'))", (data['name'], data['email'], data['message']))
        conn.commit()
    return jsonify({"message": "Message received"}), 201


@app.route('/contacts', methods=['GET'])
@admin_required
def get_contacts():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM contacts ORDER BY id DESC").fetchall()
    return jsonify([dict(r) for r in rows])


# ✅ جلب تفاصيل منتج واحد
@app.route('/products/<int:product_id>')
def get_product(product_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not row:
        return jsonify({"error": "Product not found"}), 404
    item = dict(row)
    item['image_url'] = f"http://127.0.0.1:5000/uploads/{item['image']}" if item['image'] else None
    return jsonify(item)


if __name__ == "__main__":
    app.run(debug=True)