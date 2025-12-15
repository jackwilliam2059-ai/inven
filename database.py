"""
데이터베이스 연결 설정 - Supabase PostgreSQL
"""
import os
from contextlib import contextmanager
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool
from dotenv import load_dotenv

# .env 파일 로드
import sys
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

env_path = os.path.join(BASE_DIR, '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv()

# Supabase PostgreSQL 연결 정보
# .env 파일에서 읽거나 직접 설정
SUPABASE_URL = os.getenv('SUPABASE_URL', '')
SUPABASE_KEY = os.getenv('SUPABASE_KEY', '')
ORGANIZATION_ID = os.getenv('ORGANIZATION_ID', '')

# PostgreSQL 직접 연결 정보 (Supabase 대시보드에서 확인)
# Database Settings > Connection string > URI
DATABASE_URL = os.getenv('DATABASE_URL', '')

# DATABASE_URL이 없으면 Supabase URL에서 추출
if not DATABASE_URL and SUPABASE_URL:
    # Supabase URL 형식: https://xxxxx.supabase.co
    # PostgreSQL URL 형식: postgresql://postgres:[PASSWORD]@db.xxxxx.supabase.co:5432/postgres
    supabase_project = SUPABASE_URL.replace('https://', '').replace('.supabase.co', '')
    db_password = os.getenv('SUPABASE_DB_PASSWORD', '')
    if db_password:
        DATABASE_URL = f"postgresql://postgres.{supabase_project}:{db_password}@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres"

# 엔진 생성
engine = None
SessionLocal = None
ScopedSession = None


def init_database(database_url: str = None):
    """데이터베이스 초기화"""
    global engine, SessionLocal, ScopedSession
    
    url = database_url or DATABASE_URL
    
    if not url:
        raise ValueError(
            "데이터베이스 URL이 설정되지 않았습니다.\n"
            ".env 파일에 DATABASE_URL 또는 SUPABASE_DB_PASSWORD를 설정하세요.\n\n"
            "예시:\n"
            "DATABASE_URL=postgresql://postgres.xxxxx:password@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres\n"
            "또는\n"
            "SUPABASE_DB_PASSWORD=your_password"
        )
    
    # SQLAlchemy 엔진 생성
    engine = create_engine(
        url,
        poolclass=QueuePool,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,  # 30분마다 연결 갱신
        pool_pre_ping=True,  # 연결 상태 확인
        echo=False  # SQL 로그 (디버그시 True)
    )
    
    # 세션 팩토리 생성
    SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine
    )
    
    # 스레드 안전 세션
    ScopedSession = scoped_session(SessionLocal)
    
    print(f"✅ 데이터베이스 연결 초기화 완료")
    return engine


def get_engine():
    """엔진 반환"""
    global engine
    if engine is None:
        init_database()
    return engine


def get_session():
    """새 세션 생성"""
    global SessionLocal
    if SessionLocal is None:
        init_database()
    return SessionLocal()


@contextmanager
def session_scope():
    """세션 컨텍스트 매니저 - 트랜잭션 자동 관리"""
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def get_scoped_session():
    """스레드별 세션 반환 (GUI 앱용)"""
    global ScopedSession
    if ScopedSession is None:
        init_database()
    return ScopedSession()


def remove_scoped_session():
    """스레드 세션 제거"""
    global ScopedSession
    if ScopedSession:
        ScopedSession.remove()


# 테스트용
def test_connection():
    """데이터베이스 연결 테스트"""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute("SELECT 1")
            print("✅ 데이터베이스 연결 성공!")
            return True
    except Exception as e:
        print(f"❌ 데이터베이스 연결 실패: {e}")
        return False


if __name__ == "__main__":
    test_connection()
