"""
Supabase 연결 및 데이터 조회 테스트
"""
import os
from supabase import create_client

# .env 파일 읽기
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ .env 파일 로드")
except ImportError:
    print("⚠️ python-dotenv 없음, 환경 변수 직접 확인")

# Supabase 설정
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
ORGANIZATION_ID = os.getenv("ORGANIZATION_ID", "")

print(f"\n📋 설정 확인:")
print(f"URL: {SUPABASE_URL}")
print(f"KEY: {SUPABASE_KEY[:20]}..." if SUPABASE_KEY else "KEY: (없음)")
print(f"ORG: {ORGANIZATION_ID}\n")

def test_connection():
    """연결 테스트"""
    print("🔗 Supabase 연결 테스트 시작...\n")
    
    try:
        # 클라이언트 생성
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ 클라이언트 생성 완료")
        
        # 상품 조회
        print("\n📦 상품 데이터 조회...")
        products = supabase.table('products')\
            .select('id, name, code')\
            .eq('organization_id', ORGANIZATION_ID)\
            .limit(5)\
            .execute()
        
        print(f"✅ 상품 {len(products.data)}개 조회 완료:")
        for p in products.data:
            print(f"   - ID {p['id']}: {p['name']} ({p.get('code', 'N/A')})")
        
        # 발주 조회
        print("\n📋 발주 데이터 조회...")
        orders = supabase.table('orders')\
            .select('id, order_date, quantity, status')\
            .eq('organization_id', ORGANIZATION_ID)\
            .limit(5)\
            .execute()
        
        print(f"✅ 발주 {len(orders.data)}개 조회 완료:")
        for o in orders.data:
            print(f"   - ID {o['id']}: {o['order_date']} / {o['quantity']}개 / {o['status']}")
        
        # 매장 조회
        print("\n🏪 매장 데이터 조회...")
        stores = supabase.table('stores')\
            .select('id, name, code')\
            .eq('organization_id', ORGANIZATION_ID)\
            .execute()
        
        print(f"✅ 매장 {len(stores.data)}개 조회 완료:")
        for s in stores.data:
            print(f"   - ID {s['id']}: {s['name']} ({s.get('code', 'N/A')})")
        
        print("\n✨ 모든 테스트 완료!")
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        print("\n확인 사항:")
        print("1. SUPABASE_URL이 올바른지 확인")
        print("2. SUPABASE_KEY가 anon public key인지 확인")
        print("3. ORGANIZATION_ID가 올바른지 확인")
        print("4. pip install supabase --break-system-packages 실행했는지 확인")

if __name__ == "__main__":
    test_connection()
