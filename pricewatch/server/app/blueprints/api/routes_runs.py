from flask import jsonify, request
from . import api_bp
import uuid
from datetime import datetime

# 실행 상태 저장 (실제로는 Redis나 DB 사용)
runs = {}

@api_bp.route('/runs', methods=['POST'])
def create_run():
    """크롤링 실행 생성"""
    data = request.get_json()
    
    run_id = str(uuid.uuid4())
    run_data = {
        "id": run_id,
        "platforms": data.get("platforms", []),
        "profiles": data.get("profiles", []),
        "skus": data.get("skus", []),
        "status": "created",
        "created_at": datetime.now().isoformat(),
        "progress": 0
    }
    
    runs[run_id] = run_data
    
    return jsonify({"run_id": run_id, "status": "created"}), 201

@api_bp.route('/runs/<run_id>/start', methods=['POST'])
def start_run(run_id):
    """크롤링 실행 시작"""
    if run_id not in runs:
        return jsonify({"error": "Run not found"}), 404
    
    runs[run_id]["status"] = "running"
    runs[run_id]["started_at"] = datetime.now().isoformat()
    
    # 실제로는 여기서 백그라운드 작업 시작
    
    return jsonify({"status": "started"})

@api_bp.route('/runs/<run_id>/stop', methods=['POST'])
def stop_run(run_id):
    """크롤링 실행 중지"""
    if run_id not in runs:
        return jsonify({"error": "Run not found"}), 404
    
    runs[run_id]["status"] = "stopped"
    runs[run_id]["stopped_at"] = datetime.now().isoformat()
    
    return jsonify({"status": "stopped"})

@api_bp.route('/runs/<run_id>', methods=['GET'])
def get_run(run_id):
    """크롤링 실행 상태 조회"""
    if run_id not in runs:
        return jsonify({"error": "Run not found"}), 404
    
    return jsonify(runs[run_id])

@api_bp.route('/runs', methods=['GET'])
def list_runs():
    """크롤링 실행 목록 조회"""
    return jsonify(list(runs.values()))