from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3

app = Flask(__name__)
CORS(app)

def connect_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


# صفحة رئيسية
@app.route("/")
def home():
    return "Server is running"


# تسجيل مستخدم
@app.route('/register', methods=['POST'])
def register():
    data = request.json
    conn = connect_db()
    conn.execute(
        "INSERT INTO users(name,email,password,role) VALUES (?,?,?,?)",
        (data['name'], data['email'], data['password'], 'client')
    )
    conn.commit()
    return {"message": "User created"}


# تسجيل الدخول
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    conn = connect_db()
    user = conn.execute(
        "SELECT * FROM users WHERE email=? AND password=?",
        (data['email'], data['password'])
    ).fetchone()
    if user:
        return {"role": user["role"], "id": user["id"]}
    else:
        return {"error": "Wrong login"}


# إضافة تحديث
@app.route('/add_update', methods=['POST'])
def add_update():
    data = request.json
    conn = connect_db()
    conn.execute(
        "INSERT INTO updates(title,content,date) VALUES (?,?,datetime('now'))",
        (data['title'], data['content'])
    )
    conn.commit()
    return {"message": "Update added"}


# جلب التحديثات
@app.route('/updates')
def updates():
    conn = connect_db()
    updates = conn.execute(
        "SELECT * FROM updates ORDER BY id DESC"
    ).fetchall()
    return jsonify([dict(u) for u in updates])


# تشغيل السيرفر
if __name__ == "__main__":
    app.run(debug=True)
