#!/usr/bin/env python3
"""
JSON 데이터를 Supabase로 마이그레이션
"""

import json
import os
from supabase import create_client, Client

# Supabase 설정
SUPABASE_URL = os.getenv("SUPABASE_URL", "YOUR_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "YOUR_SUPABASE_ANON_KEY")

# JSON 파일 경로
JSON_FILE = "C:\\Users\\Jack\\OneDrive\\inventory_data.json"

def load_json_data():
    """JSON 파일 로드"""
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def migrate_to_supabase():
    """Supabase로 마이그레이션"""
    
    print("=" * 60)
    print("Supabase 마이그레이션 시작")
    print("=" * 60)
    
    # Supabase 클라이언트
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # JSON 데이터 로드
    print("\n1. JSON 데이터 로드...")
    data = load_json_data()
    
    products = data.get('products', [])
    orders = data.get('orders', [])
    stores = data.get('stores', [])
    field_names = data.get('field_names', [])
    
    print(f"   상품: {len(products)}개")
    print(f"   발주: {len(orders)}개")
    print(f"   매장: {len(stores)}개")
    print(f"   필드: {len(field_names)}개")
    
    # 조직 생성
    print("\n2. 조직 생성...")
    org_result = supabase.table('organizations').insert({
        'name': '기본 조직'
    }).execute()
    
    org_id = org_result.data[0]['id']
    print(f"   조직 ID: {org_id}")
    
    # 필드 정의
    print("\n3. 필드 정의 마이그레이션...")
    for idx, field in enumerate(field_names):
        supabase.table('field_definitions').insert({
            'organization_id': org_id,
            'name': field['name'],
            'key': field['key'],
            'field_order': idx
        }).execute()
    print(f"   완료: {len(field_names)}개")
    
    # 매장
    print("\n4. 매장 마이그레이션...")
    for store in stores:
        supabase.table('stores').insert({
            'id': store.get('id', ''),
            'organization_id': org_id,
            'name': store['name']
        }).execute()
    print(f"   완료: {len(stores)}개")
    
    # 상품
    print("\n5. 상품 마이그레이션...")
    product_id_map = {}  # 기존 ID -> 새 ID 매핑
    
    for product in products:
        # dynamic_fields 추출
        dynamic_fields = {}
        for field in field_names:
            key = field['key']
            if key in product:
                dynamic_fields[key] = product[key]
        
        # 상품 삽입
        result = supabase.table('products').insert({
            'organization_id': org_id,
            'name': product['name'],
            'code': product.get('code', ''),
            'colors': product.get('colors', []),
            'sizes': product.get('sizes', ['FREE']),
            'current_stock': product.get('current_stock', 0),
            'image_path': product.get('image', ''),
            'dynamic_fields': dynamic_fields
        }).execute()
        
        new_id = result.data[0]['id']
        product_id_map[product['id']] = new_id
    
    print(f"   완료: {len(products)}개")
    
    # 발주
    print("\n6. 발주 마이그레이션...")
    for order in orders:
        old_product_id = order['product_id']
        new_product_id = product_id_map.get(old_product_id)
        
        if not new_product_id:
            print(f"   경고: 상품 ID {old_product_id}를 찾을 수 없음")
            continue
        
        supabase.table('orders').insert({
            'organization_id': org_id,
            'product_id': new_product_id,
            'order_date': order.get('date', ''),
            'color': order.get('color', ''),
            'size': order.get('size', 'FREE'),
            'quantity': order['quantity'],
            'shipped_quantity': order['shipped_quantity'],
            'status': order.get('status', 'pending'),
            'store_id': order.get('store_id', ''),
            'note': order.get('note', '')
        }).execute()
    
    print(f"   완료: {len(orders)}개")
    
    print("\n" + "=" * 60)
    print("✅ 마이그레이션 완료!")
    print("=" * 60)
    print("\n다음 단계:")
    print("1. Supabase 대시보드에서 데이터 확인")
    print("2. 이미지 파일을 Supabase Storage에 업로드")
    print("3. 애플리케이션에서 Supabase 연결 테스트")

if __name__ == '__main__':
    import sys
    
    if SUPABASE_URL == "YOUR_SUPABASE_URL":
        print("❌ 오류: SUPABASE_URL을 설정해주세요")
        print("\n환경 변수 설정:")
        print("  export SUPABASE_URL='your-project-url'")
        print("  export SUPABASE_KEY='your-anon-key'")
        sys.exit(1)
    
    try:
        migrate_to_supabase()
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
