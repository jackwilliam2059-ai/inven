"""
.env 파일 설정 확인
"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ .env 파일 로드 완료\n")
except ImportError:
    print("❌ python-dotenv가 설치되지 않았습니다")
    print("   pip install python-dotenv --break-system-packages\n")

print("="*60)
print("📋 현재 설정:")
print("="*60)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
ORGANIZATION_ID = os.getenv("ORGANIZATION_ID", "")

if SUPABASE_URL:
    print(f"✅ SUPABASE_URL: {SUPABASE_URL}")
else:
    print("❌ SUPABASE_URL: 없음")

if SUPABASE_KEY:
    print(f"✅ SUPABASE_KEY: {SUPABASE_KEY[:30]}...{SUPABASE_KEY[-10:]}")
else:
    print("❌ SUPABASE_KEY: 없음")

if ORGANIZATION_ID:
    print(f"✅ ORGANIZATION_ID: {ORGANIZATION_ID}")
else:
    print("❌ ORGANIZATION_ID: 없음")

print("="*60)

# 문제 진단
if not all([SUPABASE_URL, SUPABASE_KEY, ORGANIZATION_ID]):
    print("\n⚠️ 설정이 누락되었습니다!")
    print("\n.env 파일 위치 확인:")
    print(f"   현재 폴더: {os.getcwd()}")
    print(f"   .env 존재: {os.path.exists('.env')}")
    
    if os.path.exists('.env'):
        print("\n.env 파일 내용:")
        with open('.env', 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key = line.split('=')[0]
                    print(f"   {key}=...")
    else:
        print("\n❌ .env 파일이 없습니다!")
        print("\n.env 파일 생성 방법:")
        print("1. 메모장 열기")
        print("2. 다음 내용 입력:")
        print("   SUPABASE_URL=https://ugzfqmfqwzadgnpchpkf.supabase.co")
        print("   SUPABASE_KEY=your-service-role-key")
        print("   ORGANIZATION_ID=your-org-uuid")
        print("3. 파일 > 다른 이름으로 저장")
        print("4. 파일 형식: 모든 파일 (*.*)")
        print("5. 파일 이름: .env")
else:
    print("\n✅ 모든 설정 완료!")
    print("\n다음 단계:")
    print("   python test_supabase.py")
