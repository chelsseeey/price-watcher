from flask import jsonify
from . import api_bp

@api_bp.route('/platforms', methods=['GET'])
def get_platforms():
    """플랫폼 목록 조회"""
    platforms = [
        {"id": "agoda", "name": "Agoda", "enabled": True},
        {"id": "kayak", "name": "Kayak", "enabled": True}, 
        {"id": "coupang", "name": "쿠팡", "enabled": True}
    ]
    return jsonify(platforms)

@api_bp.route('/profiles', methods=['GET'])
def get_profiles():
    """프로필 목록 조회"""
    profiles = [
        {"id": "guest_kr_pc_search", "name": "Guest KR PC Search"},
        {"id": "guest_kr_pc_ad", "name": "Guest KR PC Ad"},
        {"id": "guest_kr_mobile_search", "name": "Guest KR Mobile Search"},
        {"id": "guest_kr_mobile_ad", "name": "Guest KR Mobile Ad"},
        {"id": "member_kr_pc_search", "name": "Member KR PC Search"},
        {"id": "member_kr_pc_ad", "name": "Member KR PC Ad"},
        {"id": "member_kr_mobile_search", "name": "Member KR Mobile Search"},
        {"id": "member_kr_mobile_ad", "name": "Member KR Mobile Ad"}
    ]
    return jsonify(profiles)

@api_bp.route('/skus/<platform>', methods=['GET'])
def get_skus(platform):
    """플랫폼별 SKU 목록 조회"""
    skus = {
        "agoda": [
            {"id": "AGODA_HOTEL_001", "name": "서울 그랜드 하얏트 호텔"},
            {"id": "AGODA_HOTEL_002", "name": "뉴욕 타임스퀘어 호텔"}
        ],
        "kayak": [
            {"id": "KAYAK_FLIGHT_001", "name": "서울-뉴욕 항공편"},
            {"id": "KAYAK_FLIGHT_002", "name": "서울-도쿄 항공편"}
        ],
        "coupang": [
            {"id": "COUPANG_PRODUCT_001", "name": "삼성 갤럭시 S24"},
            {"id": "COUPANG_PRODUCT_002", "name": "애플 아이패드 프로"}
        ]
    }
    return jsonify(skus.get(platform, []))