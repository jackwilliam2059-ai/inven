"""
특정 상품만 추가 마이그레이션 스크립트

특정 상품명 또는 상품코드를 가진 상품만 Supabase에 추가합니다.
기존 데이터는 건드리지 않고 새로운 상품만 추가합니다.

사용법:
    python add_specific_products.py
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


class SpecificProductMigrator:
    """특정 상품만 추가하는 마이그레이터"""
    
    def __init__(self, supabase_url: str, supabase_key: str, organization_id: str):
        self.supabase: Client = create_client(supabase_url, supabase_key)
        self.organization_id = organization_id
        self.added_count = 0
        self.error_count = 0
    
    def upload_image(self, product_id: str, image_base64: str) -> str:
        """Base64 이미지를 Supabase Storage에 업로드"""
        try:
            image_data = base64.b64decode(image_base64)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            file_name = f"products/{product_id}_{timestamp}.jpg"
            
            result = self.supabase.storage.from_('product-images').upload(
                file_name,
                image_data,
                file_options={"content-type": "image/jpeg"}
            )
            
            public_url = self.supabase.storage.from_('product-images').get_public_url(file_name)
            return public_url
            
        except Exception as e:
            print(f"   ⚠️  이미지 업로드 실패: {str(e)}")
            return None
    
    def product_exists(self, product_code: str) -> bool:
        """상품 코드가 이미 존재하는지 확인"""
        try:
            result = self.supabase.table('products').select('id').eq(
                'organization_id', self.organization_id
            ).eq('code', product_code).execute()
            
            return len(result.data) > 0
        except:
            return False
    
    def add_product(self, product: Dict) -> bool:
        """단일 상품 추가"""
        try:
            product_code = product.get('code')
            
            # 이미 존재하는지 확인
            if product_code and self.product_exists(product_code):
                print(f"   ⚠️  이미 존재하는 코드: {product['name']} ({product_code})")
                return False
            
            # 이미지 처리
            image_url = None
            if product.get('image'):
                print(f"   📷 이미지 업로드 중: {product['name']}")
                image_url = self.upload_image(str(product['id']), product['image'])
            
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
                print(f"   ✅ 추가 완료: {product['name']} ({product_code})")
                self.added_count += 1
                return True
            
        except Exception as e:
            self.error_count += 1
            print(f"   ❌ 오류: {product['name']} - {str(e)}")
            return False
    
    def add_products_by_name(self, json_file: str, product_name: str):
        """특정 이름의 상품들만 추가"""
        print(f"\n📦 '{product_name}' 상품 추가 시작...")
        print("="*60)
        
        # JSON 파일 로드
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        products = data.get('products', [])
        
        # 해당 이름의 상품들 찾기
        matching_products = [p for p in products if product_name.lower() in p['name'].lower()]
        
        if not matching_products:
            print(f"❌ '{product_name}' 상품을 찾을 수 없습니다.")
            return
        
        print(f"찾은 상품: {len(matching_products)}개\n")
        
        # 각 상품 추가
        for idx, product in enumerate(matching_products, 1):
            print(f"[{idx}/{len(matching_products)}] {product['name']} (코드: {product.get('code', '없음')})")
            self.add_product(product)
        
        # 결과 요약
        print("\n" + "="*60)
        print(f"✅ 추가 완료: {self.added_count}개")
        if self.error_count > 0:
            print(f"❌ 오류: {self.error_count}개")
        print("="*60)
    
    def add_products_by_codes(self, json_file: str, product_codes: List[str]):
        """특정 상품코드들만 추가"""
        print(f"\n📦 상품 코드별 추가 시작...")
        print("="*60)
        
        # JSON 파일 로드
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        products = data.get('products', [])
        
        # 해당 코드의 상품들 찾기
        matching_products = [p for p in products if p.get('code') in product_codes]
        
        if not matching_products:
            print(f"❌ 해당 코드의 상품을 찾을 수 없습니다: {product_codes}")
            return
        
        print(f"찾은 상품: {len(matching_products)}개\n")
        
        # 각 상품 추가
        for idx, product in enumerate(matching_products, 1):
            print(f"[{idx}/{len(matching_products)}] {product['name']} (코드: {product.get('code', '없음')})")
            self.add_product(product)
        
        # 결과 요약
        print("\n" + "="*60)
        print(f"✅ 추가 완료: {self.added_count}개")
        if self.error_count > 0:
            print(f"❌ 오류: {self.error_count}개")
        print("="*60)


def main():
    """메인 함수"""
    print("="*60)
    print("특정 상품 추가 마이그레이션")
    print("="*60)
    
    # 설정 입력
    print("\n📝 Supabase 설정을 입력하세요:")
    print()
    
    supabase_url = input("Supabase URL: ").strip()
    supabase_key = input("Supabase API Key (service_role): ").strip()
    organization_id = input("Organization UUID: ").strip()
    
    if not supabase_url or not supabase_key or not organization_id:
        print("\n❌ 모든 설정 값을 입력해야 합니다.")
        return
    
    # JSON 파일 경로
    json_file = input("\nJSON 파일 경로: ").strip()
    if not json_file or not os.path.exists(json_file):
        print("❌ 파일을 찾을 수 없습니다.")
        return
    
    # 추가 방식 선택
    print("\n추가 방식을 선택하세요:")
    print("1. 상품명으로 검색")
    print("2. 상품코드로 검색")
    
    choice = input("\n선택 (1 또는 2): ").strip()
    
    migrator = SpecificProductMigrator(supabase_url, supabase_key, organization_id)
    
    if choice == '1':
        product_name = input("\n상품명 입력 (부분 일치): ").strip()
        if product_name:
            migrator.add_products_by_name(json_file, product_name)
        else:
            print("❌ 상품명을 입력해야 합니다.")
    
    elif choice == '2':
        codes_input = input("\n상품코드 입력 (쉼표로 구분): ").strip()
        if codes_input:
            product_codes = [code.strip() for code in codes_input.split(',')]
            migrator.add_products_by_codes(json_file, product_codes)
        else:
            print("❌ 상품코드를 입력해야 합니다.")
    
    else:
        print("❌ 잘못된 선택입니다.")


if __name__ == '__main__':
    main()
