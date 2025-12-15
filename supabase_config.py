"""
Supabase 연결 설정
"""
import os
import sys
from dotenv import load_dotenv
from supabase import create_client

# PyInstaller 빌드 시 exe 경로, 일반 실행 시 스크립트 경로
if getattr(sys, 'frozen', False):
    # PyInstaller로 빌드된 exe 실행
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # 일반 Python 스크립트 실행
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# .env 파일 경로
env_path = os.path.join(BASE_DIR, '.env')

# .env 파일 로드
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv()  # 기본 경로 시도

# 환경 변수에서 설정 읽기
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
ORGANIZATION_ID = os.getenv('ORGANIZATION_ID')

# 설정 확인
if not all([SUPABASE_URL, SUPABASE_KEY, ORGANIZATION_ID]):
    raise ValueError(
        f"❌ Supabase 설정이 없습니다.\n"
        f".env 파일 경로: {env_path}\n"
        f".env 파일 존재: {os.path.exists(env_path)}\n\n"
        f".env 파일에 다음 항목을 설정하세요:\n"
        f"SUPABASE_URL=https://xxx.supabase.co\n"
        f"SUPABASE_KEY=your_service_role_key\n"
        f"ORGANIZATION_ID=your_org_id"
    )

# 동기 클라이언트 생성 (일반 CRUD용)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

print(f"✅ Supabase 연결 설정 완료")
