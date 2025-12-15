"""
SQLAlchemy 기반 DataManager - DB 직접 접근 버전
캐시 없이 항상 DB에서 실시간 데이터 조회
"""
import os
import sys
import json
import time
import threading
from datetime import datetime, date
from typing import Dict, List, Optional, Any, Callable
from contextlib import contextmanager

from sqlalchemy import create_engine, and_, or_, func, text
from sqlalchemy.orm import sessionmaker, scoped_session, joinedload
from sqlalchemy.pool import QueuePool
from dotenv import load_dotenv

from models import (
    Base, Organization, Store, Tag, Product, ProductTag, 
    Order, InboundRecord, OutboundRecord, InventoryMovement,
    FieldName, SettlementBalance
)

# .env 파일 로드
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

env_path = os.path.join(BASE_DIR, '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv()

# 설정
DATABASE_URL = os.getenv('DATABASE_URL', '')
ORGANIZATION_ID = os.getenv('ORGANIZATION_ID', '')


class SQLAlchemyDataManager:
    """
    SQLAlchemy 기반 데이터 매니저 - DB 직접 접근 버전
    
    핵심 원칙:
    1. DB가 Single Source of Truth (단일 진실 소스)
    2. 모든 읽기는 DB에서 직접 조회
    3. 모든 쓰기는 즉시 commit
    4. 캐시는 짧은 TTL(1초)로 성능 최적화만 담당
    """
    
    # 캐시 TTL (초) - 30초 동안 캐시 유지
    CACHE_TTL = 30.0
    
    def __init__(self, database_url: str = None, organization_id: str = None):
        self.database_url = database_url or DATABASE_URL
        self.organization_id = organization_id or ORGANIZATION_ID
        
        if not self.database_url:
            raise ValueError(
                "DATABASE_URL이 설정되지 않았습니다.\n"
                ".env 파일에 다음을 설정하세요:\n"
                "DATABASE_URL=postgresql://postgres.xxxxx:password@aws-1-ap-southeast-1.pooler.supabase.com:6543/postgres"
            )
        
        if not self.organization_id:
            raise ValueError("ORGANIZATION_ID가 설정되지 않았습니다.")
        
        # 엔진 및 세션 초기화
        self.engine = create_engine(
            self.database_url,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=1800,
            pool_pre_ping=True,
            echo=False
        )
        
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )
        
        self.ScopedSession = scoped_session(self.SessionLocal)
        
        # 캐시 및 타임스탬프 (TTL 캐시용)
        self._cache = {
            'products': {'data': [], 'time': 0},
            'orders': {'data': [], 'time': 0},
            'inbound_records': {'data': [], 'time': 0},
            'outbound_records': {'data': [], 'time': 0},
            'movements': {'data': [], 'time': 0},
            'stores': {'data': [], 'time': 0},
            'tags': {'data': [], 'time': 0},
            'field_names': {'data': [], 'time': 0},
            'settlement_balances': {'data': {}, 'time': 0},
        }
        self._cache_lock = threading.Lock()
        
        # 로컬 설정 파일 경로
        self.users_file = os.path.join(BASE_DIR, 'users.json')
        self.config_file = os.path.join(BASE_DIR, 'config.json')
        
        # 기존 호환성 속성
        self.cloud_info = None
        self.cloud_path = None
        self.cloud_type = None
        self.data_file = None
        self.lock_file = None
        
        # 컴퓨터 고유 ID 생성 (사용자 식별용)
        import socket
        import uuid
        try:
            computer_name = socket.gethostname()
            mac_addr = hex(uuid.getnode())[2:].upper()
            self.current_user = f"{computer_name}_{mac_addr[:8]}"
        except:
            self.current_user = f"user_{uuid.uuid4().hex[:8]}"
        
        # 사용자 설정 로드
        self._users_config = self._load_users_config()
        self.user_display_name = self._users_config.get('display_name', '')
        self.is_locked = False
        
        # Realtime 관련 (비활성화)
        self._on_change_callback: Optional[Callable] = None
        self._realtime_enabled = False
        
        print(f"✅ SQLAlchemy DataManager 초기화 완료 (DB 직접 접근 모드)")
    
    # ==================== 세션 관리 ====================
    
    def get_session(self):
        """새 세션 생성"""
        return self.SessionLocal()
    
    @contextmanager
    def session_scope(self):
        """세션 컨텍스트 매니저"""
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
    
    # ==================== 캐시 관리 ====================
    
    def _is_cache_valid(self, cache_name: str) -> bool:
        """캐시가 유효한지 확인 (TTL 체크)"""
        with self._cache_lock:
            cache = self._cache.get(cache_name)
            if cache and (time.time() - cache['time']) < self.CACHE_TTL:
                return True
            return False
    
    def _get_cache(self, cache_name: str):
        """캐시 데이터 가져오기"""
        with self._cache_lock:
            return self._cache[cache_name]['data']
    
    def _set_cache(self, cache_name: str, data):
        """캐시 데이터 설정"""
        with self._cache_lock:
            self._cache[cache_name] = {'data': data, 'time': time.time()}
    
    def _invalidate_cache(self, cache_name: str = None):
        """캐시 무효화"""
        with self._cache_lock:
            if cache_name:
                if cache_name in self._cache:
                    self._cache[cache_name]['time'] = 0
            else:
                # 전체 캐시 무효화
                for key in self._cache:
                    self._cache[key]['time'] = 0
    
    def invalidate_all_cache(self):
        """모든 캐시 무효화 (외부에서 호출용)"""
        self._invalidate_cache()
    
    # ==================== 데이터 Property (DB 직접 조회) ====================
    
    @property
    def products(self) -> List[Dict]:
        """상품 목록 - DB에서 조회 (TTL 캐시)"""
        if self._is_cache_valid('products'):
            return self._get_cache('products')
        return self._load_products()
    
    @products.setter
    def products(self, value):
        """호환성을 위한 setter (실제로는 캐시만 설정)"""
        self._set_cache('products', value)
    
    @property
    def orders(self) -> List[Dict]:
        """발주 목록 - DB에서 조회 (TTL 캐시)"""
        if self._is_cache_valid('orders'):
            return self._get_cache('orders')
        return self._load_orders()
    
    @orders.setter
    def orders(self, value):
        self._set_cache('orders', value)
    
    @property
    def inbound_records(self) -> List[Dict]:
        """입고 기록 - DB에서 조회 (TTL 캐시)"""
        if self._is_cache_valid('inbound_records'):
            return self._get_cache('inbound_records')
        return self._load_inbound_records()
    
    @inbound_records.setter
    def inbound_records(self, value):
        self._set_cache('inbound_records', value)
    
    @property
    def outbound_records(self) -> List[Dict]:
        """출고 기록 - DB에서 조회 (TTL 캐시)"""
        if self._is_cache_valid('outbound_records'):
            return self._get_cache('outbound_records')
        return self._load_outbound_records()
    
    @outbound_records.setter
    def outbound_records(self, value):
        self._set_cache('outbound_records', value)
    
    @property
    def movements(self) -> List[Dict]:
        """재고 이동 - DB에서 조회 (TTL 캐시)"""
        if self._is_cache_valid('movements'):
            return self._get_cache('movements')
        return self._load_movements()
    
    @movements.setter
    def movements(self, value):
        self._set_cache('movements', value)
    
    @property
    def stores(self) -> List[Dict]:
        """매장 목록 - DB에서 조회 (TTL 캐시)"""
        if self._is_cache_valid('stores'):
            return self._get_cache('stores')
        return self._load_stores()
    
    @stores.setter
    def stores(self, value):
        self._set_cache('stores', value)
    
    @property
    def tags(self) -> List[Dict]:
        """태그 목록 - DB에서 조회 (TTL 캐시)"""
        if self._is_cache_valid('tags'):
            return self._get_cache('tags')
        return self._load_tags()
    
    @tags.setter
    def tags(self, value):
        self._set_cache('tags', value)
    
    @property
    def field_names(self) -> List[Dict]:
        """필드명 - DB에서 조회 (TTL 캐시)"""
        if self._is_cache_valid('field_names'):
            return self._get_cache('field_names')
        return self._load_field_names()
    
    @field_names.setter
    def field_names(self, value):
        self._set_cache('field_names', value)
    
    @property
    def settlement_balances(self) -> Dict[str, float]:
        """정산 잔액 - DB에서 조회 (TTL 캐시)"""
        if self._is_cache_valid('settlement_balances'):
            return self._get_cache('settlement_balances')
        return self._load_settlement_balances()
    
    @settlement_balances.setter
    def settlement_balances(self, value):
        self._set_cache('settlement_balances', value)
    
    # ==================== 데이터 로드 메서드 ====================
    
    def _load_products(self) -> List[Dict]:
        """상품 DB에서 로드"""
        try:
            with self.session_scope() as session:
                products = session.query(Product)\
                    .options(joinedload(Product.product_tags).joinedload(ProductTag.tag))\
                    .filter(Product.organization_id == self.organization_id)\
                    .filter(or_(Product.is_active == True, Product.is_active == None))\
                    .order_by(Product.sort_order, Product.name)\
                    .all()
                
                result = [self._product_to_dict(p) for p in products]
                self._set_cache('products', result)
                return result
        except Exception as e:
            print(f"❌ 상품 로드 오류: {e}")
            return self._get_cache('products') or []
    
    def _load_orders(self) -> List[Dict]:
        """발주 DB에서 로드"""
        try:
            with self.session_scope() as session:
                orders = session.query(Order)\
                    .filter(Order.organization_id == self.organization_id)\
                    .order_by(Order.order_date.desc())\
                    .all()
                
                result = [self._order_to_dict(o) for o in orders]
                self._set_cache('orders', result)
                return result
        except Exception as e:
            print(f"❌ 발주 로드 오류: {e}")
            return self._get_cache('orders') or []
    
    def _load_inbound_records(self) -> List[Dict]:
        """입고 기록 DB에서 로드"""
        try:
            with self.session_scope() as session:
                records = session.query(InboundRecord)\
                    .options(joinedload(InboundRecord.product))\
                    .filter(InboundRecord.organization_id == self.organization_id)\
                    .order_by(InboundRecord.date.desc())\
                    .all()
                
                result = [self._inbound_to_dict(r) for r in records]
                self._set_cache('inbound_records', result)
                return result
        except Exception as e:
            print(f"❌ 입고 기록 로드 오류: {e}")
            return self._get_cache('inbound_records') or []
    
    def _load_outbound_records(self) -> List[Dict]:
        """출고 기록 DB에서 로드"""
        try:
            with self.session_scope() as session:
                records = session.query(OutboundRecord)\
                    .options(joinedload(OutboundRecord.product), joinedload(OutboundRecord.store))\
                    .filter(OutboundRecord.organization_id == self.organization_id)\
                    .order_by(OutboundRecord.date.desc())\
                    .all()
                
                result = [self._outbound_to_dict(r) for r in records]
                self._set_cache('outbound_records', result)
                return result
        except Exception as e:
            print(f"❌ 출고 기록 로드 오류: {e}")
            return self._get_cache('outbound_records') or []
    
    def _load_movements(self) -> List[Dict]:
        """재고 이동 DB에서 로드"""
        try:
            with self.session_scope() as session:
                movements = session.query(InventoryMovement)\
                    .options(joinedload(InventoryMovement.product))\
                    .filter(InventoryMovement.organization_id == self.organization_id)\
                    .order_by(InventoryMovement.date.desc())\
                    .all()
                
                result = [self._movement_to_dict(m) for m in movements]
                self._set_cache('movements', result)
                return result
        except Exception as e:
            print(f"❌ 재고 이동 로드 오류: {e}")
            return self._get_cache('movements') or []
    
    def _load_stores(self) -> List[Dict]:
        """매장 DB에서 로드"""
        try:
            with self.session_scope() as session:
                stores = session.query(Store)\
                    .filter(Store.organization_id == self.organization_id)\
                    .order_by(Store.id)\
                    .all()
                
                result = [self._store_to_dict(s) for s in stores]
                self._set_cache('stores', result)
                return result
        except Exception as e:
            print(f"❌ 매장 로드 오류: {e}")
            return self._get_cache('stores') or []
    
    def _load_tags(self) -> List[Dict]:
        """태그 DB에서 로드"""
        try:
            with self.session_scope() as session:
                tags = session.query(Tag)\
                    .filter(Tag.organization_id == self.organization_id)\
                    .order_by(Tag.sort_order, Tag.name)\
                    .all()
                
                result = [self._tag_to_dict(t) for t in tags]
                self._set_cache('tags', result)
                return result
        except Exception as e:
            print(f"❌ 태그 로드 오류: {e}")
            return self._get_cache('tags') or []
    
    def _load_field_names(self) -> List[Dict]:
        """필드명 DB에서 로드"""
        try:
            with self.session_scope() as session:
                field_names = session.query(FieldName)\
                    .filter(FieldName.organization_id == self.organization_id)\
                    .order_by(FieldName.field_index)\
                    .all()
                
                if field_names:
                    result = [
                        {'field_index': fn.field_index, 'name': fn.field_name}  # field_name 사용
                        for fn in field_names
                    ]
                else:
                    result = [
                        {'field_index': 0, 'name': '색상'},
                        {'field_index': 1, 'name': '사이즈'}
                    ]
                
                self._set_cache('field_names', result)
                return result
        except Exception as e:
            print(f"❌ 필드명 로드 오류: {e}")
            return [{'field_index': 0, 'name': '색상'}, {'field_index': 1, 'name': '사이즈'}]
    
    def _load_settlement_balances(self) -> Dict[str, float]:
        """정산 잔액 DB에서 로드"""
        try:
            with self.session_scope() as session:
                balances = session.query(SettlementBalance)\
                    .filter(SettlementBalance.organization_id == self.organization_id)\
                    .all()
                
                result = {str(b.store_id): float(b.balance) for b in balances}
                self._set_cache('settlement_balances', result)
                return result
        except Exception as e:
            print(f"❌ 정산 잔액 로드 오류: {e}")
            return self._get_cache('settlement_balances') or {}
    
    def load_data(self):
        """모든 데이터 로드 (호환성용 - 캐시 무효화 후 로드)"""
        self._invalidate_cache()
        
        # 각 property 접근하여 로드
        _ = self.products
        _ = self.orders
        _ = self.inbound_records
        _ = self.outbound_records
        _ = self.movements
        _ = self.stores
        _ = self.tags
        _ = self.field_names
        _ = self.settlement_balances
        
        print(f"✅ 데이터 로드 완료: 상품 {len(self.products)}개, 발주 {len(self.orders)}개")
    
    def save_data(self):
        """저장 (호환성용 - DB는 자동 커밋)"""
        print("ℹ️  DB는 자동 저장됩니다")
        return True
    
    # ==================== ORM -> Dict 변환 ====================
    
    def _product_to_dict(self, p: Product) -> Dict:
        """Product ORM -> Dict"""
        tags = []
        if p.product_tags:
            tags = [pt.tag.name for pt in p.product_tags if pt.tag]
        
        return {
            'id': p.id,
            'name': p.name,
            'code': p.code or '',
            'supplier': p.supplier or '',
            'colors': p.colors or [],
            'sizes': p.sizes or [],
            'tags': tags,
            'memo': p.memo or '',
            'order_unit': p.order_unit,
            'image': None,  # 이미지는 별도 처리
            'image_url': p.image_url,
            'image_source': 'url' if p.image_url else 'none',
            'sort_order': p.sort_order or 0,
            'is_active': p.is_active
        }
    
    def _order_to_dict(self, o: Order) -> Dict:
        """Order ORM -> Dict"""
        return {
            'id': o.id,
            'product_id': o.product_id,
            'date': o.order_date.strftime('%Y-%m-%d') if isinstance(o.order_date, (datetime, date)) else str(o.order_date),
            'color': o.color or '',
            'size': o.size or 'FREE',
            'quantity': o.quantity,
            'shipped_quantity': o.shipped_quantity or 0,
            'store_id': o.store_id,
            'status': o.status or 'pending',
            'note': o.note or ''
        }
    
    def _inbound_to_dict(self, r: InboundRecord) -> Dict:
        """InboundRecord ORM -> Dict"""
        return {
            'id': r.id,
            'product_id': r.product_id,
            'product_name': r.product.name if r.product else '',
            'product_code': r.product.code if r.product else '',  # 추가
            'date': r.date.strftime('%Y-%m-%d') if isinstance(r.date, (datetime, date)) else str(r.date),
            'quantity': r.quantity,
            'color': r.color or '',
            'size': r.size or 'FREE',
            'unit_price': float(r.unit_price) if r.unit_price else 0,
            'note': r.note or '',
            'linked_order_ids': []
        }
    
    def _outbound_to_dict(self, r: OutboundRecord) -> Dict:
        """OutboundRecord ORM -> Dict"""
        return {
            'id': r.id,
            'product_id': r.product_id,
            'product_name': r.product.name if r.product else '',
            'product_code': r.product.code if r.product else '',  # 추가
            'store_id': r.store_id,
            'store_name': r.store.name if r.store else '',
            'date': r.date.strftime('%Y-%m-%d') if isinstance(r.date, (datetime, date)) else str(r.date),
            'quantity': r.quantity,
            'color': r.color or '',
            'size': r.size or 'FREE',
            'unit_price': float(r.unit_price) if r.unit_price else 0,
            'note': r.note or ''
        }
    
    def _movement_to_dict(self, m: InventoryMovement) -> Dict:
        """InventoryMovement ORM -> Dict"""
        return {
            'id': m.id,
            'product_id': m.product_id,
            'product_name': m.product.name if m.product else '',
            'product_code': m.product.code if m.product else '',  # 추가
            'date': m.date.strftime('%Y-%m-%d') if isinstance(m.date, (datetime, date)) else str(m.date),
            'type': 'transfer',
            'quantity': m.quantity,
            'color': m.color or '',
            'size': m.size or 'FREE',
            'from_store': m.from_location or '',
            'to_store': m.to_location or '',
            'note': m.notes or ''
        }
    
    def _store_to_dict(self, s: Store) -> Dict:
        """Store ORM -> Dict"""
        return {
            'id': s.id,
            'name': s.name,
            'address': s.address or '',
            'phone': s.phone or '',
            'memo': ''  # DB에 없으므로 빈 문자열
        }
    
    def _tag_to_dict(self, t: Tag) -> Dict:
        """Tag ORM -> Dict"""
        return {
            'id': t.id,
            'name': t.name,
            'color': t.color,
            'sort_order': t.sort_order
        }
    
    # ==================== 상품 관리 ====================
    
    def get_product_by_id(self, product_id: int) -> Optional[Dict]:
        """상품 ID로 조회 (DB에서 직접)"""
        try:
            with self.session_scope() as session:
                product = session.query(Product)\
                    .options(joinedload(Product.product_tags).joinedload(ProductTag.tag))\
                    .filter(Product.id == product_id)\
                    .filter(Product.organization_id == self.organization_id)\
                    .first()
                
                if product:
                    return self._product_to_dict(product)
                return None
        except Exception as e:
            print(f"❌ 상품 조회 오류: {e}")
            # 캐시에서 찾기 (폴백)
            for p in self._get_cache('products') or []:
                if p['id'] == product_id:
                    return p
            return None
    
    def get_next_product_id(self) -> int:
        """다음 상품 ID"""
        try:
            with self.session_scope() as session:
                max_id = session.query(func.max(Product.id))\
                    .filter(Product.organization_id == self.organization_id)\
                    .scalar()
                return (max_id or 0) + 1
        except:
            return len(self.products) + 1
    
    def add_product(self, product_data: Dict) -> Dict:
        """상품 추가"""
        try:
            with self.session_scope() as session:
                product = Product(
                    organization_id=self.organization_id,
                    name=product_data.get('name'),
                    code=product_data.get('code'),
                    supplier=product_data.get('supplier'),
                    colors=product_data.get('colors', []),
                    sizes=product_data.get('sizes', []),
                    memo=product_data.get('memo'),
                    order_unit=product_data.get('order_unit'),
                    image_url=product_data.get('image_url'),
                    sort_order=product_data.get('sort_order', 0),
                    is_active=True
                )
                session.add(product)
                session.flush()
                
                # 태그 연결
                if 'tags' in product_data and product_data['tags']:
                    for tag_name in product_data['tags']:
                        tag = session.query(Tag).filter(
                            Tag.organization_id == self.organization_id,
                            Tag.name == tag_name
                        ).first()
                        if tag:
                            pt = ProductTag(product_id=product.id, tag_id=tag.id)
                            session.add(pt)
                
                result = self._product_to_dict(product)
                result['tags'] = product_data.get('tags', [])
                
            # 캐시 무효화
            self._invalidate_cache('products')
            print(f"✅ 상품 추가: {result['name']} (ID: {result['id']})")
            return result
                
        except Exception as e:
            print(f"❌ 상품 추가 오류: {e}")
            raise
    
    def update_product(self, product_id: int, updates: Dict) -> bool:
        """상품 수정"""
        try:
            with self.session_scope() as session:
                product = session.query(Product).filter(
                    Product.id == product_id,
                    Product.organization_id == self.organization_id
                ).first()
                
                if not product:
                    print(f"⚠️ 상품을 찾을 수 없음: ID={product_id}")
                    return False
                
                # 업데이트 가능한 필드
                for key in ['name', 'code', 'supplier', 'colors', 'sizes', 
                           'memo', 'order_unit', 'image_url', 'sort_order', 'is_active']:
                    if key in updates:
                        setattr(product, key, updates[key])
                
                # 태그 업데이트
                if 'tags' in updates:
                    session.query(ProductTag).filter(
                        ProductTag.product_id == product_id
                    ).delete()
                    
                    for tag_name in updates['tags']:
                        tag = session.query(Tag).filter(
                            Tag.organization_id == self.organization_id,
                            Tag.name == tag_name
                        ).first()
                        if tag:
                            pt = ProductTag(product_id=product.id, tag_id=tag.id)
                            session.add(pt)
            
            # 캐시 무효화
            self._invalidate_cache('products')
            print(f"✅ 상품 수정: ID={product_id}")
            return True
                
        except Exception as e:
            print(f"❌ 상품 수정 오류: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def update_product_in_db(self, product_id: int, product_dict: Dict) -> bool:
        """상품 DB 업데이트 (호환성용)"""
        updates = {
            'name': product_dict.get('name'),
            'code': product_dict.get('code'),
            'supplier': product_dict.get('supplier'),
            'colors': product_dict.get('colors', []),
            'sizes': product_dict.get('sizes', []),
            'memo': product_dict.get('memo'),
            'order_unit': product_dict.get('order_unit'),
            'image_url': product_dict.get('image_url'),
            'sort_order': product_dict.get('sort_order', 0),
            'is_active': product_dict.get('is_active', True)
        }
        if 'tags' in product_dict:
            updates['tags'] = product_dict['tags']
        
        return self.update_product(product_id, updates)
    
    def delete_product(self, product_id: int) -> bool:
        """상품 삭제 (soft delete)"""
        return self.update_product(product_id, {'is_active': False})
    
    def delete_product_from_db(self, product_id: int) -> bool:
        """상품 DB에서 삭제 (호환성용)"""
        result = self.delete_product(product_id)
        if result:
            print(f"✅ 상품 삭제: ID={product_id}")
        return result
    
    # ==================== 발주 관리 ====================
    
    def get_order_by_id(self, order_id: int) -> Optional[Dict]:
        """발주 ID로 조회"""
        try:
            with self.session_scope() as session:
                order = session.query(Order).filter(
                    Order.id == order_id,
                    Order.organization_id == self.organization_id
                ).first()
                
                if order:
                    return self._order_to_dict(order)
                return None
        except:
            return None
    
    def add_order(self, order_data: Dict) -> Dict:
        """발주 추가"""
        try:
            with self.session_scope() as session:
                order = Order(
                    organization_id=self.organization_id,
                    product_id=order_data['product_id'],
                    order_date=order_data.get('date', datetime.now().strftime('%Y-%m-%d')),
                    color=order_data.get('color'),
                    size=order_data.get('size', 'FREE'),
                    quantity=order_data['quantity'],
                    shipped_quantity=order_data.get('shipped_quantity', 0),
                    store_id=order_data.get('store_id'),
                    status=order_data.get('status', 'pending'),
                    note=order_data.get('note', '')
                )
                session.add(order)
                session.flush()
                
                result = self._order_to_dict(order)
            
            self._invalidate_cache('orders')
            print(f"✅ 발주 추가: ID={result['id']}")
            return result
                
        except Exception as e:
            print(f"❌ 발주 추가 오류: {e}")
            raise
    
    def update_order(self, order_id: int, updates: Dict) -> bool:
        """발주 수정"""
        try:
            with self.session_scope() as session:
                order = session.query(Order).filter(
                    Order.id == order_id,
                    Order.organization_id == self.organization_id
                ).first()
                
                if not order:
                    return False
                
                for key in ['product_id', 'order_date', 'color', 'size', 
                           'quantity', 'shipped_quantity', 'store_id', 'status', 'note']:
                    if key in updates:
                        # date 필드명 매핑
                        db_key = 'order_date' if key == 'date' else key
                        setattr(order, db_key, updates[key])
            
            self._invalidate_cache('orders')
            return True
                
        except Exception as e:
            print(f"❌ 발주 수정 오류: {e}")
            return False
    
    def delete_order(self, order_id: int) -> bool:
        """발주 삭제"""
        try:
            with self.session_scope() as session:
                result = session.query(Order).filter(
                    Order.id == order_id,
                    Order.organization_id == self.organization_id
                ).delete()
            
            self._invalidate_cache('orders')
            return result > 0
                
        except Exception as e:
            print(f"❌ 발주 삭제 오류: {e}")
            return False
    
    def update_order_shipped(self, order_id: int, shipped_qty: int) -> bool:
        """발주 입고 수량 업데이트"""
        return self.update_order(order_id, {'shipped_quantity': shipped_qty})
    
    # ==================== 입고 관리 ====================
    
    def add_inbound(self, inbound_data: Dict) -> Dict:
        """입고 추가"""
        try:
            with self.session_scope() as session:
                record = InboundRecord(
                    organization_id=self.organization_id,
                    product_id=inbound_data['product_id'],
                    date=inbound_data.get('date', datetime.now().strftime('%Y-%m-%d')),
                    quantity=inbound_data['quantity'],
                    color=inbound_data.get('color'),
                    size=inbound_data.get('size', 'FREE'),
                    unit_price=inbound_data.get('unit_price', 0),
                    note=inbound_data.get('note', '')
                    # linked_order_ids는 DB에 없으므로 제거
                )
                session.add(record)
                session.flush()
                
                result = self._inbound_to_dict(record)
            
            self._invalidate_cache('inbound_records')
            return result
                
        except Exception as e:
            print(f"❌ 입고 추가 오류: {e}")
            raise
    
    def update_inbound(self, record_id: int, updates: Dict) -> bool:
        """입고 수정"""
        try:
            with self.session_scope() as session:
                record = session.query(InboundRecord).filter(
                    InboundRecord.id == record_id,
                    InboundRecord.organization_id == self.organization_id
                ).first()
                
                if not record:
                    return False
                
                for key in ['product_id', 'date', 'quantity', 'color', 'size', 
                           'unit_price', 'note']:  # linked_order_ids 제거
                    if key in updates:
                        setattr(record, key, updates[key])
            
            self._invalidate_cache('inbound_records')
            return True
                
        except Exception as e:
            print(f"❌ 입고 수정 오류: {e}")
            return False
    
    def delete_inbound(self, record_id: int) -> bool:
        """입고 삭제"""
        try:
            with self.session_scope() as session:
                result = session.query(InboundRecord).filter(
                    InboundRecord.id == record_id,
                    InboundRecord.organization_id == self.organization_id
                ).delete()
            
            self._invalidate_cache('inbound_records')
            return result > 0
                
        except Exception as e:
            print(f"❌ 입고 삭제 오류: {e}")
            return False
    
    # ==================== 출고 관리 ====================
    
    def add_outbound(self, outbound_data: Dict) -> Dict:
        """출고 추가"""
        try:
            with self.session_scope() as session:
                record = OutboundRecord(
                    organization_id=self.organization_id,
                    product_id=outbound_data['product_id'],
                    store_id=outbound_data.get('store_id'),
                    date=outbound_data.get('date', datetime.now().strftime('%Y-%m-%d')),
                    quantity=outbound_data['quantity'],
                    color=outbound_data.get('color'),
                    size=outbound_data.get('size', 'FREE'),
                    unit_price=outbound_data.get('unit_price', 0),
                    note=outbound_data.get('note', '')
                )
                session.add(record)
                session.flush()
                
                result = self._outbound_to_dict(record)
            
            self._invalidate_cache('outbound_records')
            return result
                
        except Exception as e:
            print(f"❌ 출고 추가 오류: {e}")
            raise
    
    def update_outbound(self, record_id: int, updates: Dict) -> bool:
        """출고 수정"""
        try:
            with self.session_scope() as session:
                record = session.query(OutboundRecord).filter(
                    OutboundRecord.id == record_id,
                    OutboundRecord.organization_id == self.organization_id
                ).first()
                
                if not record:
                    return False
                
                for key in ['product_id', 'store_id', 'date', 'quantity', 
                           'color', 'size', 'unit_price', 'note']:
                    if key in updates:
                        setattr(record, key, updates[key])
            
            self._invalidate_cache('outbound_records')
            return True
                
        except Exception as e:
            print(f"❌ 출고 수정 오류: {e}")
            return False
    
    def delete_outbound(self, record_id: int) -> bool:
        """출고 삭제"""
        try:
            with self.session_scope() as session:
                result = session.query(OutboundRecord).filter(
                    OutboundRecord.id == record_id,
                    OutboundRecord.organization_id == self.organization_id
                ).delete()
            
            self._invalidate_cache('outbound_records')
            return result > 0
                
        except Exception as e:
            print(f"❌ 출고 삭제 오류: {e}")
            return False
    
    # ==================== 재고 이동 관리 ====================
    
    def add_movement(self, movement_data: Dict) -> Dict:
        """재고 이동 추가"""
        try:
            with self.session_scope() as session:
                movement = InventoryMovement(
                    organization_id=self.organization_id,
                    product_id=movement_data['product_id'],
                    date=movement_data.get('date', datetime.now().strftime('%Y-%m-%d')),
                    quantity=movement_data['quantity'],
                    color=movement_data.get('color'),
                    size=movement_data.get('size', 'FREE'),
                    from_location=movement_data.get('from_store'),  # from_store -> from_location
                    to_location=movement_data.get('to_store'),      # to_store -> to_location
                    notes=movement_data.get('note', '')             # note -> notes
                )
                session.add(movement)
                session.flush()
                
                result = self._movement_to_dict(movement)
            
            self._invalidate_cache('movements')
            return result
                
        except Exception as e:
            print(f"❌ 재고 이동 추가 오류: {e}")
            raise
    
    def delete_movement(self, movement_id: int) -> bool:
        """재고 이동 삭제"""
        try:
            with self.session_scope() as session:
                result = session.query(InventoryMovement).filter(
                    InventoryMovement.id == movement_id,
                    InventoryMovement.organization_id == self.organization_id
                ).delete()
            
            self._invalidate_cache('movements')
            return result > 0
                
        except Exception as e:
            print(f"❌ 재고 이동 삭제 오류: {e}")
            return False
    
    # ==================== 매장 관리 ====================
    
    def get_store_by_id(self, store_id) -> Optional[Dict]:
        """매장 ID로 조회"""
        if not store_id:
            return None
        
        store_id_str = str(store_id)
        for s in self.stores:
            if str(s['id']) == store_id_str:
                return s
        return None
    
    def add_store(self, store_data: Dict) -> Dict:
        """매장 추가"""
        try:
            with self.session_scope() as session:
                store = Store(
                    organization_id=self.organization_id,
                    name=store_data['name'],
                    address=store_data.get('address'),
                    phone=store_data.get('phone')
                    # memo는 DB에 없으므로 제거
                )
                session.add(store)
                session.flush()
                
                result = self._store_to_dict(store)
            
            self._invalidate_cache('stores')
            return result
                
        except Exception as e:
            print(f"❌ 매장 추가 오류: {e}")
            raise
    
    def update_store(self, store_id: int, updates: Dict) -> bool:
        """매장 수정"""
        try:
            with self.session_scope() as session:
                store = session.query(Store).filter(
                    Store.id == store_id,
                    Store.organization_id == self.organization_id
                ).first()
                
                if not store:
                    return False
                
                for key in ['name', 'address', 'phone']:  # memo 제거
                    if key in updates:
                        setattr(store, key, updates[key])
            
            self._invalidate_cache('stores')
            return True
                
        except Exception as e:
            print(f"❌ 매장 수정 오류: {e}")
            return False
    
    def delete_store(self, store_id: int) -> bool:
        """매장 삭제"""
        try:
            with self.session_scope() as session:
                result = session.query(Store).filter(
                    Store.id == store_id,
                    Store.organization_id == self.organization_id
                ).delete()
            
            self._invalidate_cache('stores')
            return result > 0
                
        except Exception as e:
            print(f"❌ 매장 삭제 오류: {e}")
            return False
    
    # ==================== 태그 관리 ====================
    
    def get_tag_by_name(self, tag_name: str) -> Optional[Dict]:
        """태그 이름으로 조회"""
        for t in self.tags:
            if t['name'] == tag_name:
                return t
        return None
    
    def add_tag(self, tag_data: Dict) -> Dict:
        """태그 추가"""
        try:
            with self.session_scope() as session:
                tag = Tag(
                    organization_id=self.organization_id,
                    name=tag_data['name'],
                    color=tag_data.get('color'),
                    sort_order=tag_data.get('sort_order', 0)
                )
                session.add(tag)
                session.flush()
                
                result = self._tag_to_dict(tag)
            
            self._invalidate_cache('tags')
            return result
                
        except Exception as e:
            print(f"❌ 태그 추가 오류: {e}")
            raise
    
    def update_tag(self, tag_id: int, updates: Dict) -> bool:
        """태그 수정"""
        try:
            with self.session_scope() as session:
                tag = session.query(Tag).filter(
                    Tag.id == tag_id,
                    Tag.organization_id == self.organization_id
                ).first()
                
                if not tag:
                    return False
                
                for key in ['name', 'color', 'sort_order']:
                    if key in updates:
                        setattr(tag, key, updates[key])
            
            self._invalidate_cache('tags')
            return True
                
        except Exception as e:
            print(f"❌ 태그 수정 오류: {e}")
            return False
    
    def delete_tag(self, tag_id: int) -> bool:
        """태그 삭제"""
        try:
            with self.session_scope() as session:
                # 연결된 ProductTag도 삭제
                session.query(ProductTag).filter(ProductTag.tag_id == tag_id).delete()
                result = session.query(Tag).filter(
                    Tag.id == tag_id,
                    Tag.organization_id == self.organization_id
                ).delete()
            
            self._invalidate_cache('tags')
            self._invalidate_cache('products')  # 상품의 태그 정보도 갱신 필요
            return result > 0
                
        except Exception as e:
            print(f"❌ 태그 삭제 오류: {e}")
            return False
    
    # ==================== 필드명 관리 ====================
    
    def update_field_name(self, field_index: int, name: str) -> bool:
        """필드명 수정"""
        try:
            with self.session_scope() as session:
                field = session.query(FieldName).filter(
                    FieldName.organization_id == self.organization_id,
                    FieldName.field_index == field_index
                ).first()
                
                if field:
                    field.field_name = name  # field_name 컬럼 사용
                else:
                    field = FieldName(
                        organization_id=self.organization_id,
                        field_index=field_index,
                        field_name=name  # field_name 컬럼 사용
                    )
                    session.add(field)
            
            self._invalidate_cache('field_names')
            return True
                
        except Exception as e:
            print(f"❌ 필드명 수정 오류: {e}")
            return False
    
    # ==================== 정산 잔액 관리 ====================
    
    def get_settlement_balance(self, store_id) -> float:
        """매장별 정산 잔액 조회"""
        return self.settlement_balances.get(str(store_id), 0.0)
    
    def update_settlement_balance(self, store_id, amount: float) -> bool:
        """정산 잔액 업데이트"""
        try:
            with self.session_scope() as session:
                balance = session.query(SettlementBalance).filter(
                    SettlementBalance.organization_id == self.organization_id,
                    SettlementBalance.store_id == str(store_id)
                ).first()
                
                if balance:
                    balance.balance = amount
                else:
                    balance = SettlementBalance(
                        organization_id=self.organization_id,
                        store_id=str(store_id),
                        balance=amount
                    )
                    session.add(balance)
            
            self._invalidate_cache('settlement_balances')
            return True
                
        except Exception as e:
            print(f"❌ 정산 잔액 업데이트 오류: {e}")
            return False
    
    # ==================== 재고 계산 ====================
    
    def calculate_stock(self, product_id: int) -> int:
        """총 재고 계산 (입고 - 출고)"""
        inbound = sum(r['quantity'] for r in self.inbound_records if r['product_id'] == product_id)
        outbound = sum(r['quantity'] for r in self.outbound_records if r['product_id'] == product_id)
        return inbound - outbound
    
    def calculate_stock_by_variant(self, product_id: int, color: str, size: str) -> int:
        """색상/사이즈별 재고 계산"""
        inbound = sum(
            r['quantity'] for r in self.inbound_records 
            if r['product_id'] == product_id 
            and r.get('color') == color 
            and r.get('size') == size
        )
        outbound = sum(
            r['quantity'] for r in self.outbound_records 
            if r['product_id'] == product_id 
            and r.get('color') == color 
            and r.get('size') == size
        )
        return inbound - outbound
    
    def calculate_pending(self, product_id: int) -> int:
        """총 미입고 계산"""
        return sum(
            o['quantity'] - o.get('shipped_quantity', 0)
            for o in self.orders
            if o['product_id'] == product_id
            and o.get('status', 'pending') == 'pending'
        )
    
    def calculate_pending_by_variant(self, product_id: int, color: str, size: str) -> int:
        """색상/사이즈별 미입고 계산"""
        return sum(
            o['quantity'] - o.get('shipped_quantity', 0)
            for o in self.orders
            if o['product_id'] == product_id
            and o.get('color') == color
            and o.get('size') == size
            and o.get('status', 'pending') == 'pending'
        )
    
    # ==================== 설정 관련 ====================
    
    def get_auto_split_setting(self) -> bool:
        """색상별 자동 분리 설정 가져오기"""
        config = self.load_config()
        return config.get('auto_split_colors', False)
    
    def set_auto_split_setting(self, value: bool):
        """색상별 자동 분리 설정 저장"""
        config = self.load_config()
        config['auto_split_colors'] = value
        self.save_config(config)
    
    def load_config(self) -> dict:
        """로컬 설정 로드"""
        if self.config_file and os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ 설정 로드 실패: {e}")
        return {}
    
    def save_config(self, config: dict):
        """로컬 설정 저장"""
        if self.config_file:
            try:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(config, f, ensure_ascii=False, indent=2)
                return True
            except Exception as e:
                print(f"⚠️ 설정 저장 실패: {e}")
        return False
    
    # ==================== 사용자 설정 ====================
    
    def _load_users_config(self) -> dict:
        """로컬 사용자 설정 로드"""
        if self.users_file and os.path.exists(self.users_file):
            try:
                with open(self.users_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ 사용자 설정 로드 실패: {e}")
        return {}
    
    def load_users_config(self) -> dict:
        """로컬 사용자 설정 로드 (외부용)"""
        return self._load_users_config()
    
    def save_users_config(self, config: dict):
        """로컬 사용자 설정 저장"""
        if self.users_file:
            try:
                with open(self.users_file, 'w', encoding='utf-8') as f:
                    json.dump(config, f, ensure_ascii=False, indent=2)
                self._users_config = config
                self.user_display_name = config.get('display_name', '')
                return True
            except Exception as e:
                print(f"⚠️ 사용자 설정 저장 실패: {e}")
        return False
    
    # ==================== 호환성 메서드 ====================
    
    def check_lock(self):
        """잠금 확인 (호환성)"""
        return False, None
    
    def update_lock(self):
        """잠금 갱신 (호환성)"""
        pass
    
    def release_lock(self):
        """잠금 해제 (호환성)"""
        pass
    
    def backup_data(self) -> Optional[Dict]:
        """데이터 백업"""
        return {
            'products': self.products,
            'orders': self.orders,
            'inbound_records': self.inbound_records,
            'outbound_records': self.outbound_records,
            'movements': self.movements,
            'stores': self.stores,
            'tags': self.tags,
            'field_names': self.field_names,
            'settlement_balances': self.settlement_balances,
            'backup_time': datetime.now().isoformat(),
            'current_user': self.current_user
        }
    
    def restore_from_backup(self, data: Dict):
        """백업에서 복원 (호환성)"""
        pass
    
    def check_and_restore_backup(self) -> Optional[Dict]:
        """백업 확인 및 복원 (호환성) - DB 모드에서는 불필요"""
        return None
    
    def save_backup(self, data: Dict = None):
        """백업 저장 (호환성)"""
        pass
    
    def auto_backup_data(self):
        """자동 백업 (호환성) - DB 모드에서는 불필요"""
        pass
    
    def check_and_fix_duplicate_ids(self) -> int:
        """중복 ID 확인 및 수정 (호환성) - DB에서는 자동 관리됨"""
        return 0
    
    # ==================== Realtime (비활성화) ====================
    
    def set_on_change_callback(self, callback: Callable):
        """변경 콜백 설정"""
        self._on_change_callback = callback
    
    def start_realtime(self):
        """Realtime 시작 (비활성화됨)"""
        print("ℹ️  Realtime 동기화가 비활성화되었습니다 (DB 직접 접근 모드)")
    
    def stop_realtime(self):
        """Realtime 중지"""
        self._realtime_enabled = False


# 테스트용
if __name__ == "__main__":
    dm = SQLAlchemyDataManager()
    print(f"상품: {len(dm.products)}개")
    print(f"발주: {len(dm.orders)}개")
    print(f"매장: {len(dm.stores)}개")
