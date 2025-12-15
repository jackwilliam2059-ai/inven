"""
재고관리 시스템 JSON → Supabase 마이그레이션 스크립트

기존 JSON 파일 기반 데이터를 Supabase PostgreSQL로 마이그레이션합니다.

사용법:
    pip install supabase
    python migrate_to_supabase.py

필수 설정:
    - Supabase 프로젝트 URL
    - Supabase API Key (service_role key 권장)
    - Organization UUID (미리 생성 필요)
"""

import json
import os
import base64
from datetime import datetime
from typing import Dict, List, Any
import sys

try:
    from supabase import create_client, Client
except ImportError:
    print("❌ supabase 패키지가 설치되어 있지 않습니다.")
    print("다음 명령어로 설치하세요: pip install supabase")
    sys.exit(1)


class SupabaseMigrator:
    """JSON 데이터를 Supabase로 마이그레이션하는 클래스"""
    
    def __init__(self, supabase_url: str, supabase_key: str, organization_id: str):
        """
        Args:
            supabase_url: Supabase 프로젝트 URL
            supabase_key: Supabase API Key (service_role 권장)
            organization_id: 조직 UUID
        """
        self.supabase: Client = create_client(supabase_url, supabase_key)
        self.organization_id = organization_id
        self.id_mapping: Dict[str, str] = {}  # 기존 ID → 새 UUID 매핑
        self.original_stores: List[Dict] = []  # store_id 매핑용
        self.stats = {
            'products': 0,
            'orders': 0,
            'inbound_records': 0,
            'outbound_records': 0,
            'movements': 0,
            'stores': 0,
            'field_names': 0,
            'errors': 0
        }
    
    def load_json_data(self, file_path: str = 'inventory_data.json') -> Dict[str, Any]:
        """JSON 파일 로드"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def upload_image(self, product_id: str, image_base64: str) -> str:
        """
        Base64 이미지를 Supabase Storage에 업로드
        
        Args:
            product_id: 상품 ID (파일명으로 사용)
            image_base64: Base64 인코딩된 이미지
        
        Returns:
            Public URL
        """
        try:
            # Base64 디코딩
            image_data = base64.b64decode(image_base64)
            
            # 파일명 생성 (타임스탬프 추가로 충돌 방지)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            file_name = f"products/{product_id}_{timestamp}.jpg"
            
            # Supabase Storage에 업로드
            result = self.supabase.storage.from_('product-images').upload(
                file_name,
                image_data,
                file_options={"content-type": "image/jpeg"}
            )
            
            # Public URL 가져오기
            public_url = self.supabase.storage.from_('product-images').get_public_url(file_name)
            
            return public_url
            
        except Exception as e:
            print(f"   ⚠️  이미지 업로드 실패: {str(e)}")
            return None
    
    def migrate_products(self, products: List[Dict]) -> Dict[str, str]:
        """
        상품 데이터 마이그레이션
        
        Args:
            products: 상품 리스트
        
        Returns:
            ID 매핑 딕셔너리 {old_id: new_uuid}
        """
        print("\n📦 상품 마이그레이션 시작...")
        id_mapping = {}
        inserted_codes = set()  # 이미 삽입된 코드 추적
        
        for idx, product in enumerate(products, 1):
            try:
                # 중복 코드 체크
                product_code = product.get('code')
                if product_code and product_code in inserted_codes:
                    print(f"   ⚠️  [{idx}/{len(products)}] 중복 코드 건너뜀: {product['name']} ({product_code})")
                    # ID 매핑만 추가 (같은 코드의 첫 번째 상품으로 매핑)
                    # 이미 삽입된 제품의 UUID를 찾아서 매핑
                    for old_id, new_uuid in id_mapping.items():
                        old_product = next((p for p in products if str(p['id']) == old_id), None)
                        if old_product and old_product.get('code') == product_code:
                            id_mapping[str(product['id'])] = new_uuid
                            break
                    continue
                
                # 이미지 처리
                image_url = None
                if product.get('image'):
                    print(f"   [{idx}/{len(products)}] 이미지 업로드 중: {product['name']}")
                    image_url = self.upload_image(product['id'], product['image'])
                
                # 상품 데이터 준비
                product_data = {
                    'organization_id': self.organization_id,
                    'name': product['name'],
                    'code': product_code,
                    'supplier': product.get('supplier'),
                    'colors': product.get('colors', []),
                    'sizes': product.get('sizes', ['FREE']),
                    'memo': product.get('memo'),
                    'order_unit': product.get('order_unit'),
                    'image_url': image_url,
                    'image_source': product.get('image_source', 'none')
                }
                
                # Supabase에 삽입
                result = self.supabase.table('products').insert(product_data).execute()
                
                if result.data:
                    new_id = result.data[0]['id']
                    # 문자열로 변환하여 저장 (JSON의 ID가 숫자일 수 있음)
                    id_mapping[str(product['id'])] = new_id
                    if product_code:
                        inserted_codes.add(product_code)  # 삽입된 코드 기록
                    self.stats['products'] += 1
                    print(f"   ✓ [{idx}/{len(products)}] {product['name']}")
                
            except Exception as e:
                self.stats['errors'] += 1
                print(f"   ❌ [{idx}/{len(products)}] 오류: {product['name']} - {str(e)}")
        
        print(f"✅ 상품 마이그레이션 완료: {self.stats['products']}개")
        return id_mapping
    
    def migrate_orders_as_outbound(self, orders: List[Dict]):
        """
        기존 orders를 outbound_records로 마이그레이션
        (Version 2의 orders는 실제로 매장 출고 데이터)
        """
        print("\n📤 출고 기록(orders) 마이그레이션 시작...")
        print("   ℹ️  Version 2의 'orders'는 매장 출고 데이터입니다.")
        
        for idx, order in enumerate(orders, 1):
            try:
                # 상품 ID 매핑
                new_product_id = self.id_mapping.get(str(order['product_id']))
                if not new_product_id:
                    print(f"   ⚠️  [{idx}/{len(orders)}] 상품 ID를 찾을 수 없음: {order['product_id']}")
                    continue
                
                # 매장명 찾기 (store_id로부터)
                store_name = None
                if 'store_id' in order:
                    store_id = order['store_id']
                    # stores에서 매장명 찾기
                    for store in self.original_stores:
                        if store.get('id') == store_id:
                            store_name = store.get('name')
                            break
                
                # date 필드 사용
                outbound_date = order.get('date')
                if not outbound_date:
                    print(f"   ⚠️  [{idx}/{len(orders)}] 출고일 없음")
                    continue
                
                # outbound_records로 삽입
                record_data = {
                    'organization_id': self.organization_id,
                    'product_id': new_product_id,
                    'store': store_name or order.get('store') or '알 수 없음',
                    'color': order.get('color'),
                    'size': order.get('size'),
                    'quantity': order.get('quantity', 0),
                    'box_quantity': order.get('box_quantity'),
                    'date': outbound_date,
                    'settlement_date': order.get('settlement_date')
                }
                
                # Supabase에 삽입
                self.supabase.table('outbound_records').insert(record_data).execute()
                self.stats['outbound_records'] += 1
                
                if idx % 50 == 0:
                    print(f"   진행 중... {idx}/{len(orders)}")
                
            except Exception as e:
                self.stats['errors'] += 1
                print(f"   ❌ [{idx}/{len(orders)}] 오류: {str(e)}")
        
        print(f"✅ 출고 기록 마이그레이션 완료: {self.stats['outbound_records']}개")
    
    def migrate_orders(self, orders: List[Dict]):
        """발주 데이터 마이그레이션"""
        print("\n📋 발주 마이그레이션 시작...")
        
        skipped_odd_ids = 0
        
        for idx, order in enumerate(orders, 1):
            try:
                # 상품 ID 매핑
                product_id = order['product_id']
                new_product_id = self.id_mapping.get(str(product_id))
                
                # 홀수 ID 폴백: 이전 병합으로 홀수 ID가 짝수 ID로 통합됨
                if not new_product_id and product_id % 2 == 1:
                    next_even_id = product_id + 1
                    new_product_id = self.id_mapping.get(str(next_even_id))
                    if new_product_id:
                        skipped_odd_ids += 1
                        if skipped_odd_ids <= 3:  # 처음 3개만 출력
                            print(f"   ℹ️  ID {product_id} → {next_even_id}로 매핑 (병합된 상품)")
                
                if not new_product_id:
                    print(f"   ⚠️  [{idx}/{len(orders)}] 상품 ID를 찾을 수 없음: {product_id}")
                    continue
                
                # 발주 데이터 생성
                order_data = {
                    'organization_id': self.organization_id,
                    'product_id': new_product_id,
                    'order_date': order.get('date'),
                    'color': order.get('color'),
                    'size': order.get('size', 'FREE'),
                    'quantity': order.get('quantity', 0),
                    'shipped_quantity': order.get('shipped_quantity', 0),
                    'status': order.get('status', 'pending'),
                    'store_id': str(order.get('store_id', '')),
                    'note': order.get('note', '')
                }
                
                # Supabase에 삽입
                self.supabase.table('orders').insert(order_data).execute()
                self.stats['orders'] += 1
                
                if idx % 50 == 0:
                    print(f"   진행 중... {idx}/{len(orders)}")
                
            except Exception as e:
                self.stats['errors'] += 1
                print(f"   ❌ [{idx}/{len(orders)}] 오류: {str(e)}")
        
        if skipped_odd_ids > 0:
            print(f"   ℹ️  병합된 상품으로 매핑: {skipped_odd_ids}개")
        print(f"✅ 발주 마이그레이션 완료: {self.stats['orders']}개")
    
    def migrate_inbound_records(self, records: List[Dict]):
        """입고 기록 마이그레이션"""
        print("\n📥 입고 기록 마이그레이션 시작...")
        
        for idx, record in enumerate(records, 1):
            try:
                new_product_id = self.id_mapping.get(str(record['product_id']))
                if not new_product_id:
                    continue
                
                record_data = {
                    'organization_id': self.organization_id,
                    'product_id': new_product_id,
                    'supplier': record.get('supplier'),
                    'color': record.get('color'),
                    'size': record.get('size'),
                    'quantity': record.get('quantity', 0),
                    'box_quantity': record.get('box_quantity'),
                    'received_boxes': record.get('received_boxes'),
                    'date': record.get('date'),
                    'settlement_date': record.get('settlement_date')
                }
                
                self.supabase.table('inbound_records').insert(record_data).execute()
                self.stats['inbound_records'] += 1
                
                if idx % 50 == 0:
                    print(f"   진행 중... {idx}/{len(records)}")
                
            except Exception as e:
                self.stats['errors'] += 1
                print(f"   ❌ 오류: {str(e)}")
        
        print(f"✅ 입고 기록 마이그레이션 완료: {self.stats['inbound_records']}개")
    
    def migrate_outbound_records(self, records: List[Dict]):
        """출고 기록 마이그레이션"""
        print("\n📤 출고 기록 마이그레이션 시작...")
        
        for idx, record in enumerate(records, 1):
            try:
                new_product_id = self.id_mapping.get(str(record['product_id']))
                if not new_product_id:
                    continue
                
                # date 필드 유연하게 처리
                outbound_date = record.get('date') or record.get('outbound_date')
                if not outbound_date:
                    print(f"   ⚠️  [{idx}/{len(records)}] 출고일 없음")
                    continue
                
                record_data = {
                    'organization_id': self.organization_id,
                    'product_id': new_product_id,
                    'store': record.get('store'),
                    'color': record.get('color'),
                    'size': record.get('size'),
                    'quantity': record.get('quantity', 0),
                    'box_quantity': record.get('box_quantity'),
                    'date': outbound_date,
                    'settlement_date': record.get('settlement_date')
                }
                
                self.supabase.table('outbound_records').insert(record_data).execute()
                self.stats['outbound_records'] += 1
                
                if idx % 50 == 0:
                    print(f"   진행 중... {idx}/{len(records)}")
                
            except Exception as e:
                self.stats['errors'] += 1
                print(f"   ❌ 오류: {str(e)}")
        
        print(f"✅ 출고 기록 마이그레이션 완료: {self.stats['outbound_records']}개")
    
    def migrate_movements(self, movements: List[Dict]):
        """재고 이동 마이그레이션"""
        print("\n🚚 재고 이동 마이그레이션 시작...")
        
        for idx, movement in enumerate(movements, 1):
            try:
                new_product_id = self.id_mapping.get(str(movement['product_id']))
                if not new_product_id:
                    continue
                
                movement_data = {
                    'organization_id': self.organization_id,
                    'product_id': new_product_id,
                    'color': movement.get('color'),
                    'size': movement.get('size'),
                    'quantity': movement.get('quantity', 0),
                    'box_quantity': movement.get('box_quantity'),
                    'from_location': movement.get('from_location'),
                    'to_location': movement.get('to_location'),
                    'date': movement.get('date')
                }
                
                self.supabase.table('inventory_movements').insert(movement_data).execute()
                self.stats['movements'] += 1
                
                if idx % 50 == 0:
                    print(f"   진행 중... {idx}/{len(movements)}")
                
            except Exception as e:
                self.stats['errors'] += 1
                print(f"   ❌ 오류: {str(e)}")
        
        print(f"✅ 재고 이동 마이그레이션 완료: {self.stats['movements']}개")
    
    def migrate_stores(self, stores: List[Dict]):
        """매장/거래처 마이그레이션"""
        print("\n🏪 매장 마이그레이션 시작...")
        
        for idx, store in enumerate(stores, 1):
            try:
                store_data = {
                    'organization_id': self.organization_id,
                    'name': store.get('name'),
                    'code': store.get('code'),
                    'settlement_balance': store.get('balance', 0)
                }
                
                self.supabase.table('stores').insert(store_data).execute()
                self.stats['stores'] += 1
                print(f"   ✓ [{idx}/{len(stores)}] {store.get('name')}")
                
            except Exception as e:
                self.stats['errors'] += 1
                print(f"   ❌ 오류: {str(e)}")
        
        print(f"✅ 매장 마이그레이션 완료: {self.stats['stores']}개")
    
    def migrate_field_names(self, field_names: List[Dict]):
        """필드명 설정 마이그레이션"""
        print("\n📝 필드명 설정 마이그레이션 시작...")
        
        for idx, field in enumerate(field_names, 1):
            try:
                # 다양한 키 이름 지원 (index, field_index 등)
                field_index = field.get('index') or field.get('field_index') or (idx - 1)
                field_name = field.get('name') or field.get('field_name') or f'필드{idx}'
                
                field_data = {
                    'organization_id': self.organization_id,
                    'field_index': field_index,
                    'field_name': field_name
                }
                
                self.supabase.table('field_names').insert(field_data).execute()
                self.stats['field_names'] += 1
                print(f"   ✓ 필드 {field_index}: {field_name}")
                
            except Exception as e:
                self.stats['errors'] += 1
                print(f"   ❌ 오류: {str(e)}")
        
        print(f"✅ 필드명 설정 마이그레이션 완료: {self.stats['field_names']}개")
    
    def migrate_app_settings(self, settings: Dict):
        """앱 설정 마이그레이션"""
        print("\n⚙️  앱 설정 마이그레이션 시작...")
        
        try:
            settings_data = {
                'organization_id': self.organization_id,
                'settings': settings
            }
            
            self.supabase.table('app_settings').insert(settings_data).execute()
            print("✅ 앱 설정 마이그레이션 완료")
            
        except Exception as e:
            print(f"❌ 앱 설정 마이그레이션 오류: {str(e)}")
    
    def print_summary(self):
        """마이그레이션 결과 요약 출력"""
        print("\n" + "="*60)
        print("📊 마이그레이션 결과 요약")
        print("="*60)
        print(f"✅ 상품:           {self.stats['products']:>6}개")
        print(f"✅ 발주:           {self.stats['orders']:>6}개")
        print(f"✅ 입고 기록:      {self.stats['inbound_records']:>6}개")
        print(f"✅ 출고 기록:      {self.stats['outbound_records']:>6}개")
        print(f"✅ 재고 이동:      {self.stats['movements']:>6}개")
        print(f"✅ 매장:           {self.stats['stores']:>6}개")
        print(f"✅ 필드명 설정:    {self.stats['field_names']:>6}개")
        print(f"{'❌ 오류:           ' + str(self.stats['errors']) + '개' if self.stats['errors'] > 0 else ''}")
        print("="*60)
    
    def run_migration(self, json_file: str = 'inventory_data.json'):
        """전체 마이그레이션 실행"""
        print("\n🚀 재고관리 시스템 마이그레이션 시작")
        print(f"📁 파일: {json_file}")
        print(f"🏢 조직 ID: {self.organization_id}")
        print("="*60)
        
        # JSON 데이터 로드
        data = self.load_json_data(json_file)
        
        # stores를 먼저 저장 (orders 마이그레이션에서 매장명 찾기 위함)
        self.original_stores = data.get('stores', [])
        
        # 순차적으로 마이그레이션
        self.id_mapping = self.migrate_products(data.get('products', []))
        
        # 매장 먼저 마이그레이션
        self.migrate_stores(data.get('stores', []))
        
        # 발주 마이그레이션
        self.migrate_orders(data.get('orders', []))
        
        # 나머지 데이터
        self.migrate_inbound_records(data.get('inbound_records', []))
        # self.migrate_outbound_records(data.get('outbound_records', []))  # orders로 이미 처리됨
        self.migrate_movements(data.get('movements', []))
        self.migrate_field_names(data.get('field_names', []))
        
        # 앱 설정 (있는 경우)
        if 'app_settings' in data:
            self.migrate_app_settings(data['app_settings'])
        
        # 결과 요약
        self.print_summary()
        
        print("\n✨ 마이그레이션이 완료되었습니다!")


def main():
    """메인 함수"""
    print("="*60)
    print("재고관리 시스템 - Supabase 마이그레이션")
    print("="*60)
    
    # 설정 입력
    print("\n📝 Supabase 설정을 입력하세요:")
    print("(Supabase Dashboard > Settings > API에서 확인)")
    print()
    
    supabase_url = input("Supabase URL: ").strip()
    supabase_key = input("Supabase API Key (service_role 권장): ").strip()
    organization_id = input("Organization UUID: ").strip()
    
    if not supabase_url or not supabase_key or not organization_id:
        print("\n❌ 모든 설정 값을 입력해야 합니다.")
        return
    
    # JSON 파일 경로
    json_file = input("\nJSON 파일 경로 (기본: inventory_data.json): ").strip()
    if not json_file:
        json_file = 'inventory_data.json'
    
    # 확인
    print("\n" + "="*60)
    print("⚠️  주의: 이 작업은 되돌릴 수 없습니다!")
    print("="*60)
    confirm = input("\n계속하시겠습니까? (yes/no): ").strip().lower()
    
    if confirm != 'yes':
        print("❌ 마이그레이션이 취소되었습니다.")
        return
    
    # 마이그레이션 실행
    try:
        migrator = SupabaseMigrator(supabase_url, supabase_key, organization_id)
        migrator.run_migration(json_file)
    except FileNotFoundError as e:
        print(f"\n❌ 파일 오류: {str(e)}")
    except Exception as e:
        print(f"\n❌ 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
