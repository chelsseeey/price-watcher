from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'your-secret-key-here'
    
    # CORS 설정 (React와 통신용)
    CORS(app)
    
    # SocketIO 설정
    socketio = SocketIO(app, cors_allowed_origins="*")
    
    # 블루프린트 등록
    from app.blueprints.api import api_bp
    app.register_blueprint(api_bp, url_prefix='/api')
    
    # 기본 라우트
    @app.route('/')
    def index():
        return {"message": "PriceWatch API Server", "status": "running"}
    
    return app, socketio