#!/usr/bin/env python3
from flask import Flask
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/')
def hello():
    return {"message": "Hello World!", "status": "working"}

@app.route('/api/test')
def test():
    return {"test": "API is working!"}

if __name__ == '__main__':
    print("🔥 Simple Flask Test Server Starting...")
    print("🌐 http://localhost:8000")
    app.run(host='0.0.0.0', port=8000, debug=True) 