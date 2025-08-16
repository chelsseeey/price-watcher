#!/usr/bin/env python3
"""
PriceWatch Flask 서버 실행
"""

from app import create_app

if __name__ == '__main__':
    app, socketio = create_app()
    
    print("🚀 PriceWatch Server Starting...")
    print("📊 Dashboard: http://localhost:8000")
    print("🔌 API: http://localhost:8000/api")
    
    # SocketIO 없이 기본 Flask 실행
    app.run(host='0.0.0.0', port=8000, debug=True) 