"""
Supabase DataManager - Version 3 with Async Realtime
기존 data_manager.py와 호환되는 인터페이스 제공
실시간 동기화 지원 (비동기 클라이언트)
"""
import os
import asyncio
import threading
from typing import List, Dict, Optional, Callable
from datetime import datetime
from supabase_config import supabase, ORGANIZATION_ID, SUPABASE_URL, SUPABASE_KEY


class DataManager:
    """Supabase 데이터 관리 (기존 인터페이스 호환 + Async Realtime)"""
    
    def __init__(self, config_file="cloud_config.json"):
        self.supabase = supabase  # 동기 클라이언트 (일반 CRUD용)
        self.organization_id = ORGANIZATION_ID
        
        # 기존 호환 속성
        self.config_file = config_file
        self.data_file = "supabase"
        self.lock_file = None  # Supabase는 lock 불필요
        self.cloud_path = None
        self.cloud_type = "Supabase"
        self.cloud_info = {"type": "Supabase", "path": "Cloud"}
        self.users_file = "users_config.json"
        
        # 사용자 관련 (호환성)
        self.current_user = os.getenv("USERNAME", "Supabase User")
        self.user_display_name = self.current_user
        self.is_locked = False
        
        # 메모리 캐시 (기존 코드와 호환)
        self.products = []
        self.orders = []
        self.movements = []
        self.inbound_records = []
        self.outbound_records = []
        self.stores = []
        self.field_names = []
        self.settlement_balances = {}
        
        # 자동 분할 설정 (호환성)
        self._auto_split = False
        
        # Realtime 관련
        self._on_change_callback = None
        self._realtime_enabled = False
        self._async_client = None
        self._realtime_loop = None
        self._realtime_thread = None
        self._channels = []
    
    # ==================== 기존 호환 메서드 ====================
    
    def load_users_config(self):
        """사용자 설정 로드 (로컬 파일)"""
        import json
        try:
            if os.path.exists(self.users_file):
                with open(self.users_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"사용자 설정 로드 오류: {e}")
        return {}
    
    def save_users_config(self, users_config):
        """사용자 설정 저장 (로컬 파일)"""
        import json
        try:
            with open(self.users_file, 'w', encoding='utf-8') as f:
                json.dump(users_config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"사용자 설정 저장 오류: {e}")
    
    def load_cloud_path(self):
        """클라우드 경로 로드 (호환성)"""
        return {"type": "Supabase", "path": "Cloud"}
    
    def save_cloud_path(self, path, cloud_type):
        """클라우드 경로 저장 (no-op)"""
        pass
    
    def load_app_settings(self):
        """앱 설정 로드 (호환성)"""
        return {"auto_split": self._auto_split}
    
    def save_app_settings(self, settings):
        """앱 설정 저장"""
        self._auto_split = settings.get("auto_split", False)
    
    def get_auto_split_setting(self):
        """자동 분할 설정 조회"""
        return self._auto_split
    
    def set_auto_split_setting(self, value):
        """자동 분할 설정 저장"""
        self._auto_split = value
    
    def check_lock(self):
        """락 확인 (Supabase는 항상 잠금 없음)"""
        return False, None  # (locked, user_name)
    
    def acquire_lock(self):
        """락 획득 (Supabase는 항상 True)"""
        return True
    
    def release_lock(self):
        """락 해제 (no-op)"""
        pass
    
    def update_lock(self):
        """락 갱신 (no-op)"""
        pass
    
    def auto_backup_data(self):
        """자동 백업 (Supabase는 자동 백업됨)"""
        pass
    
    def check_and_restore_backup(self):
        """백업 확인 및 복원 (no-op)"""
        return None
    
    # ==================== 데이터 로드/저장 ====================
    
    def load_data(self):
        """Supabase에서 데이터 로드"""
        try:
            # 상품
            response = self.supabase.table('products')\
                .select('*')\
                .eq('organization_id', self.organization_id)\
                .order('id')\
                .execute()
            self.products = response.data
            
            # 발주
            response = self.supabase.table('orders')\
                .select('*')\
                .eq('organization_id', self.organization_id)\
                .order('order_date')\
                .execute()
            
            # Supabase 구조 → 기존 구조 변환
            self.orders = []
            for order in response.data:
                # store_id를 정수로 변환 (None이면 None 유지)
                store_id = order.get('store_id')
                if store_id is not None and store_id != '':
                    try:
                        store_id = int(store_id)
                    except (ValueError, TypeError):
                        store_id = None
                else:
                    store_id = None
                    
                self.orders.append({
                    'id': order['id'],
                    'date': order['order_date'],
                    'product_id': order['product_id'],
                    'color': order['color'],
                    'size': order['size'],
                    'quantity': order['quantity'],
                    'shipped_quantity': order.get('shipped_quantity', 0),
                    'status': order.get('status', 'pending'),
                    'store_id': store_id,
                    'note': order.get('note', '')
                })
            
            # 입고 기록
            response = self.supabase.table('inbound_records')\
                .select('*, products(name, code)')\
                .eq('organization_id', self.organization_id)\
                .execute()
            
            # product_name, product_code 평탄화
            self.inbound_records = []
            for record in response.data:
                flat_record = {**record}
                if 'products' in flat_record and flat_record['products']:
                    flat_record['product_name'] = flat_record['products']['name']
                    flat_record['product_code'] = flat_record['products'].get('code', '')
                    del flat_record['products']
                else:
                    flat_record['product_name'] = '알 수 없음'
                    flat_record['product_code'] = ''
                self.inbound_records.append(flat_record)
            
            # 출고 기록
            response = self.supabase.table('outbound_records')\
                .select('*, products(name, code)')\
                .eq('organization_id', self.organization_id)\
                .execute()
            
            self.outbound_records = []
            for record in response.data:
                flat_record = {**record}
                if 'products' in flat_record and flat_record['products']:
                    flat_record['product_name'] = flat_record['products']['name']
                    flat_record['product_code'] = flat_record['products'].get('code', '')
                    del flat_record['products']
                else:
                    flat_record['product_name'] = '알 수 없음'
                    flat_record['product_code'] = ''
                self.outbound_records.append(flat_record)
            
            # 재고 이동
            response = self.supabase.table('inventory_movements')\
                .select('*')\
                .eq('organization_id', self.organization_id)\
                .execute()
            
            # type 필드 추가 (호환성)
            self.movements = []
            for movement in response.data:
                movement['type'] = 'in'  # 기본값 (창고 입고)
                movement['store_id'] = movement.get('store_id') or None
                movement['note'] = movement.get('notes', '')  # notes → note
                self.movements.append(movement)
            
            # 매장
            response = self.supabase.table('stores')\
                .select('*')\
                .eq('organization_id', self.organization_id)\
                .execute()
            self.stores = response.data
            print(f"📍 매장 로드: {len(self.stores)}개 - {[s.get('name') for s in self.stores]}")
            
            # 필드명
            response = self.supabase.table('field_names')\
                .select('*')\
                .eq('organization_id', self.organization_id)\
                .order('field_index')\
                .execute()
            
            if response.data:
                self.field_names = [
                    {'id': f'field{f["field_index"]+1}', 'name': f['field_name']}
                    for f in response.data
                ]
            else:
                self.field_names = [
                    {'id': 'field1', 'name': '색상'},
                    {'id': 'field2', 'name': '사이즈'}
                ]
            
            print(f"✅ Supabase 데이터 로드 완료: 상품 {len(self.products)}개, 발주 {len(self.orders)}개")
            return True
            
        except Exception as e:
            print(f"❌ Supabase 로드 오류: {e}")
            return False
    
    def save_data(self):
        """저장 (Supabase는 즉시 저장되므로 no-op)"""
        print("ℹ️  Supabase는 자동 저장됩니다")
        return True
    
    # ==================== Async Realtime 기능 ====================
    
    def set_on_change_callback(self, callback: Callable):
        """데이터 변경 시 호출될 콜백 설정"""
        self._on_change_callback = callback
    
    def start_realtime(self):
        """Realtime 구독 시작 (비동기)"""
        if self._realtime_enabled:
            return
        
        self._realtime_enabled = True
        
        # 별도 스레드에서 asyncio 이벤트 루프 실행
        self._realtime_thread = threading.Thread(target=self._run_realtime_loop, daemon=True)
        self._realtime_thread.start()
        
        print("🔴 Realtime 구독 시작")
    
    def stop_realtime(self):
        """Realtime 구독 중지"""
        self._realtime_enabled = False
        
        # 이벤트 루프 중지
        if self._realtime_loop and self._realtime_loop.is_running():
            self._realtime_loop.call_soon_threadsafe(self._realtime_loop.stop)
        
        print("⬛ Realtime 구독 중지")
    
    def _run_realtime_loop(self):
        """비동기 이벤트 루프 실행 (별도 스레드)"""
        try:
            self._realtime_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._realtime_loop)
            self._realtime_loop.run_until_complete(self._setup_realtime())
            self._realtime_loop.run_forever()
        except Exception as e:
            print(f"⚠️ Realtime 루프 오류: {e}")
        finally:
            if self._realtime_loop:
                self._realtime_loop.close()
    
    async def _setup_realtime(self):
        """Realtime 채널 설정 (비동기)"""
        try:
            from supabase._async.client import create_client as create_async_client
            
            # 비동기 클라이언트 생성
            self._async_client = await create_async_client(SUPABASE_URL, SUPABASE_KEY)
            
            # 테이블별 구독
            tables = ['products', 'orders', 'inbound_records', 'outbound_records', 
                      'inventory_movements', 'stores']
            
            for table in tables:
                channel = self._async_client.channel(f'db-{table}')
                
                channel.on_postgres_changes(
                    event='*',
                    schema='public',
                    table=table,
                    callback=lambda payload, t=table: self._handle_change(t, payload)
                )
                
                await channel.subscribe()
                self._channels.append(channel)
            
            print(f"✅ {len(tables)}개 테이블 구독 완료")
            
        except ImportError:
            print("⚠️ 비동기 클라이언트 없음, 폴링 모드로 전환")
            await self._polling_fallback()
        except Exception as e:
            print(f"⚠️ Realtime 설정 실패: {e}, 폴링 모드로 전환")
            await self._polling_fallback()
    
    async def _polling_fallback(self):
        """Realtime 실패 시 폴링으로 대체"""
        import hashlib
        
        def get_hash():
            data_str = f"{len(self.products)}:{len(self.orders)}:{len(self.inbound_records)}:{len(self.outbound_records)}"
            return hashlib.md5(data_str.encode()).hexdigest()
        
        last_hash = get_hash()
        
        while self._realtime_enabled:
            await asyncio.sleep(5)  # 5초마다 (30초에서 변경)
            
            if not self._realtime_enabled:
                break
            
            try:
                self.load_data()
                new_hash = get_hash()
                
                if new_hash != last_hash:
                    last_hash = new_hash
                    print(f"📡 폴링: 데이터 변경 감지")
                    if self._on_change_callback:
                        self._on_change_callback('data', 'UPDATE')
            except Exception as e:
                print(f"⚠️ 폴링 오류: {e}")
    
    def _handle_change(self, table: str, payload: dict):
        """Realtime 변경 이벤트 처리"""
        try:
            event_type = payload.get('eventType', payload.get('type', ''))
            new_record = payload.get('new', payload.get('record', {}))
            old_record = payload.get('old', {})
            
            print(f"📡 Realtime: {table} - {event_type}")
            
            # 캐시 업데이트
            cache_map = {
                'products': self.products,
                'orders': self.orders,
                'inbound_records': self.inbound_records,
                'outbound_records': self.outbound_records,
                'inventory_movements': self.movements,
                'stores': self.stores
            }
            
            cache = cache_map.get(table)
            if cache is not None:
                # orders는 형식 변환 필요
                if table == 'orders' and new_record:
                    # store_id를 정수로 변환
                    store_id = new_record.get('store_id')
                    if store_id is not None and store_id != '':
                        try:
                            store_id = int(store_id)
                        except (ValueError, TypeError):
                            store_id = None
                    else:
                        store_id = None
                    
                    new_record = {
                        'id': new_record.get('id'),
                        'date': new_record.get('order_date'),
                        'product_id': new_record.get('product_id'),
                        'color': new_record.get('color'),
                        'size': new_record.get('size'),
                        'quantity': new_record.get('quantity'),
                        'shipped_quantity': new_record.get('shipped_quantity', 0),
                        'status': new_record.get('status', 'pending'),
                        'store_id': store_id,
                        'note': new_record.get('note', '')
                    }
                
                # inventory_movements는 필드 변환
                if table == 'inventory_movements' and new_record:
                    new_record['type'] = 'in'
                    new_record['note'] = new_record.get('notes', '')
                
                self._update_cache(cache, event_type, new_record, old_record)
            
            # UI 콜백 호출
            if self._on_change_callback:
                self._on_change_callback(table, event_type)
                
        except Exception as e:
            print(f"⚠️ 변경 처리 오류: {e}")
    
    def _update_cache(self, cache_list: list, event_type: str, new_record: dict, old_record: dict):
        """캐시 리스트 업데이트"""
        event_type = event_type.upper()
        
        if event_type == 'INSERT' and new_record:
            if not any(r.get('id') == new_record.get('id') for r in cache_list):
                cache_list.append(new_record)
        elif event_type == 'UPDATE' and new_record:
            for i, r in enumerate(cache_list):
                if r.get('id') == new_record.get('id'):
                    cache_list[i] = new_record
                    break
        elif event_type == 'DELETE':
            record_id = old_record.get('id') if old_record else new_record.get('id')
            if record_id:
                cache_list[:] = [r for r in cache_list if r.get('id') != record_id]
    
    # ==================== 상품 관리 ====================
    
    def get_product_by_id(self, product_id):
        """상품 ID로 조회"""
        for product in self.products:
            if product['id'] == product_id:
                return product
        return None
    
    def get_next_product_id(self):
        """다음 상품 ID (Supabase auto increment)"""
        if not self.products:
            return 1
        return max(p['id'] for p in self.products) + 1
    
    def check_and_fix_duplicate_ids(self):
        """중복 ID 확인 (Supabase는 자동 처리)"""
        return []
    
    # ==================== 매장 관리 ====================
    
    def get_store_by_id(self, store_id):
        """매장 ID로 조회"""
        if not store_id:
            return None
        for store in self.stores:
            # 문자열/정수 모두 처리
            if str(store.get('id', '')) == str(store_id):
                return store
        return None
    
    # ==================== 재고 계산 ====================
    
    def calculate_stock(self, product_id):
        """총 재고 계산"""
        total_inbound = sum(
            r['quantity'] for r in self.inbound_records
            if r['product_id'] == product_id
        )
        total_outbound = sum(
            r['quantity'] for r in self.outbound_records
            if r['product_id'] == product_id
        )
        return total_inbound - total_outbound
    
    def calculate_stock_by_variant(self, product_id, color, size):
        """색상/사이즈별 재고 계산"""
        total_inbound = sum(
            r['quantity'] for r in self.inbound_records
            if r['product_id'] == product_id
            and r.get('color') == color
            and r.get('size') == size
        )
        total_outbound = sum(
            r['quantity'] for r in self.outbound_records
            if r['product_id'] == product_id
            and r.get('color') == color
            and r.get('size') == size
        )
        return total_inbound - total_outbound
    
    def calculate_pending(self, product_id):
        """총 미입고 계산"""
        return sum(
            o['quantity'] - o.get('shipped_quantity', 0)
            for o in self.orders
            if o['product_id'] == product_id
            and o.get('status', 'pending') == 'pending'
        )
    
    def calculate_pending_by_variant(self, product_id, color, size):
        """색상/사이즈별 미입고 계산"""
        return sum(
            o['quantity'] - o.get('shipped_quantity', 0)
            for o in self.orders
            if o['product_id'] == product_id
            and o.get('color') == color
            and o.get('size') == size
            and o.get('status', 'pending') == 'pending'
        )
    
    # ==================== Supabase 전용 메서드 ====================
    
    def add_product(self, product: Dict) -> Dict:
        """상품 추가 (Supabase에 저장 + 메모리 추가)"""
        try:
            # Supabase 테이블 스키마에 맞게 필드 변환
            # image, image_source 등은 Supabase에 없으므로 제외
            db_product = {
                'organization_id': self.organization_id,
                'name': product.get('name'),
                'code': product.get('code'),
                'supplier': product.get('supplier'),
                'colors': product.get('colors', []),
                'sizes': product.get('sizes', []),
                'memo': product.get('memo', ''),
                'order_unit': product.get('order_unit')
            }
            
            response = self.supabase.table('products').insert(db_product).execute()
            new_product = response.data[0]
            
            # 로컬 전용 필드 추가 (image 등)
            new_product['image'] = product.get('image')
            new_product['image_source'] = product.get('image_source')
            
            self.products.append(new_product)
            print(f"✅ 상품 DB 저장: {new_product.get('name')}")
            return new_product
        except Exception as e:
            print(f"❌ 상품 DB 저장 오류: {e}")
            import traceback
            traceback.print_exc()
            # 로컬에만 추가
            product['id'] = self.get_next_product_id()
            self.products.append(product)
            return product
    
    def add_product_to_db(self, product: Dict) -> Dict:
        """상품 추가 (Supabase) - 기존 호환용"""
        return self.add_product(product)
    
    def add_order(self, order: Dict) -> Dict:
        """발주 추가 (Supabase에 저장 + 메모리 추가)"""
        try:
            # store_id를 정수로 변환
            store_id = order.get('store_id')
            if store_id is not None and store_id != '':
                try:
                    store_id = int(store_id)
                except (ValueError, TypeError):
                    store_id = None
            else:
                store_id = None
            
            db_order = {
                'organization_id': self.organization_id,
                'product_id': order['product_id'],
                'order_date': order.get('date') or order.get('order_date'),
                'color': order.get('color'),
                'size': order.get('size', 'FREE'),
                'quantity': order['quantity'],
                'shipped_quantity': order.get('shipped_quantity', 0),
                'status': order.get('status', 'pending'),
                'store_id': store_id,
                'note': order.get('note', '')
            }
            
            response = self.supabase.table('orders').insert(db_order).execute()
            new_order = response.data[0]
            
            # store_id 다시 정수로 변환
            new_store_id = new_order.get('store_id')
            if new_store_id is not None and new_store_id != '':
                try:
                    new_store_id = int(new_store_id)
                except (ValueError, TypeError):
                    new_store_id = None
            else:
                new_store_id = None
            
            # 메모리에 추가 (기존 형식)
            memory_order = {
                'id': new_order['id'],
                'date': new_order['order_date'],
                'product_id': new_order['product_id'],
                'color': new_order['color'],
                'size': new_order['size'],
                'quantity': new_order['quantity'],
                'shipped_quantity': new_order['shipped_quantity'],
                'status': new_order['status'],
                'store_id': new_store_id,
                'note': new_order.get('note', '')
            }
            self.orders.append(memory_order)
            print(f"✅ 발주 DB 저장: product_id={new_order['product_id']}, qty={new_order['quantity']}, store_id={new_store_id}")
            return memory_order
        except Exception as e:
            print(f"❌ 발주 DB 저장 오류: {e}")
            import traceback
            traceback.print_exc()
            # 로컬에만 추가
            order['id'] = len(self.orders) + 1
            if 'date' not in order and 'order_date' in order:
                order['date'] = order['order_date']
            self.orders.append(order)
            return order
    
    def add_order_to_db(self, order: Dict) -> Dict:
        """발주 추가 (Supabase) - 기존 호환용"""
        return self.add_order(order)
    
    def add_inbound(self, record: Dict) -> Dict:
        """입고 추가 (Supabase에 저장 + 메모리 추가)"""
        try:
            db_record = {
                'organization_id': self.organization_id,
                'product_id': record['product_id'],
                'date': record['date'],
                'quantity': record['quantity'],
                'color': record.get('color'),
                'size': record.get('size', 'FREE'),
                'note': record.get('note', ''),
                'supplier': record.get('supplier', '')
            }
            
            response = self.supabase.table('inbound_records').insert(db_record).execute()
            new_record = response.data[0]
            
            # 메모리에 추가
            self.inbound_records.append(new_record)
            print(f"✅ 입고 DB 저장: product_id={new_record['product_id']}, qty={new_record['quantity']}")
            return new_record
        except Exception as e:
            print(f"❌ 입고 DB 저장 오류: {e}")
            import traceback
            traceback.print_exc()
            record['id'] = len(self.inbound_records) + 1
            self.inbound_records.append(record)
            return record
    
    def add_inbound_record_to_db(self, record: Dict) -> Dict:
        """입고 추가 (Supabase) - 기존 호환용"""
        return self.add_inbound(record)
    
    def add_outbound(self, record: Dict) -> Dict:
        """출고 추가 (Supabase에 저장 + 메모리 추가)"""
        try:
            db_record = {
                'organization_id': self.organization_id,
                'product_id': record['product_id'],
                'date': record['date'],
                'quantity': record['quantity'],
                'color': record.get('color'),
                'size': record.get('size', 'FREE'),
                'store_id': str(record.get('store_id', '')) if record.get('store_id') else None,
                'note': record.get('note', '')
            }
            
            response = self.supabase.table('outbound_records').insert(db_record).execute()
            new_record = response.data[0]
            
            # 메모리에 추가
            self.outbound_records.append(new_record)
            print(f"✅ 출고 DB 저장: product_id={new_record['product_id']}, qty={new_record['quantity']}")
            return new_record
        except Exception as e:
            print(f"❌ 출고 DB 저장 오류: {e}")
            import traceback
            traceback.print_exc()
            record['id'] = len(self.outbound_records) + 1
            self.outbound_records.append(record)
            return record
    
    def add_outbound_record_to_db(self, record: Dict) -> Dict:
        """출고 추가 (Supabase) - 기존 호환용"""
        return self.add_outbound(record)
    
    def add_movement(self, movement: Dict) -> Dict:
        """재고이동 추가 (Supabase에 저장 + 메모리 추가)"""
        try:
            db_movement = {
                'organization_id': self.organization_id,
                'product_id': movement['product_id'],
                'date': movement['date'],
                'quantity': movement['quantity'],
                'color': movement.get('color'),
                'size': movement.get('size', 'FREE'),
                'from_location': movement.get('from_location', ''),
                'to_location': movement.get('to_location', ''),
                'notes': movement.get('note', '')  # note → notes
            }
            
            response = self.supabase.table('inventory_movements').insert(db_movement).execute()
            new_movement = response.data[0]
            
            # 메모리에 추가 (기존 형식)
            new_movement['type'] = movement.get('type', 'in')
            new_movement['note'] = new_movement.get('notes', '')
            self.movements.append(new_movement)
            print(f"✅ 재고이동 DB 저장: {movement.get('from_location')} → {movement.get('to_location')}")
            return new_movement
            return new_movement
        except Exception as e:
            print(f"❌ 재고이동 DB 저장 오류: {e}")
            import traceback
            traceback.print_exc()
            movement['id'] = len(self.movements) + 1
            self.movements.append(movement)
            return movement
    
    def add_movement_to_db(self, movement: Dict) -> Dict:
        """재고이동 추가 (Supabase) - 기존 호환용"""
        return self.add_movement(movement)
    
    def update_product_in_db(self, product_id: int, updates: Dict):
        """상품 수정 (Supabase)"""
        # Supabase에 없는 필드 제외
        db_updates = {k: v for k, v in updates.items() 
                      if k not in ['id', 'image', 'image_source']}
        
        if db_updates:
            self.supabase.table('products')\
                .update(db_updates)\
                .eq('id', product_id)\
                .execute()
        
        # 메모리 업데이트 (image 포함)
        for i, p in enumerate(self.products):
            if p['id'] == product_id:
                self.products[i].update(updates)
                break
    
    def delete_product_from_db(self, product_id: int):
        """상품 삭제 (Supabase)"""
        self.supabase.table('products')\
            .delete()\
            .eq('id', product_id)\
            .execute()
        
        # 메모리 삭제
        self.products = [p for p in self.products if p['id'] != product_id]
    
    def update_order_in_db(self, order_id: int, updates: Dict):
        """발주 수정 (Supabase)"""
        # 기존 형식 → Supabase 형식 변환
        db_updates = {}
        if 'date' in updates:
            db_updates['order_date'] = updates['date']
        if 'product_id' in updates:
            db_updates['product_id'] = updates['product_id']
        if 'color' in updates:
            db_updates['color'] = updates['color']
        if 'size' in updates:
            db_updates['size'] = updates['size']
        if 'quantity' in updates:
            db_updates['quantity'] = updates['quantity']
        if 'shipped_quantity' in updates:
            db_updates['shipped_quantity'] = updates['shipped_quantity']
        if 'status' in updates:
            db_updates['status'] = updates['status']
        if 'store_id' in updates:
            db_updates['store_id'] = str(updates['store_id'])
        if 'note' in updates:
            db_updates['note'] = updates['note']
        
        self.supabase.table('orders')\
            .update(db_updates)\
            .eq('id', order_id)\
            .execute()
        
        # 메모리 업데이트
        for i, o in enumerate(self.orders):
            if o['id'] == order_id:
                self.orders[i].update(updates)
                break
    
    def delete_order_from_db(self, order_id: int):
        """발주 삭제 (Supabase)"""
        self.supabase.table('orders')\
            .delete()\
            .eq('id', order_id)\
            .execute()
        
        # 메모리 삭제
        self.orders = [o for o in self.orders if o['id'] != order_id]
    
    def update_inbound_record_in_db(self, record_id: int, updates: Dict):
        """입고 기록 수정 (Supabase)"""
        self.supabase.table('inbound_records')\
            .update(updates)\
            .eq('id', record_id)\
            .execute()
        
        # 메모리 업데이트
        for i, r in enumerate(self.inbound_records):
            if r['id'] == record_id:
                self.inbound_records[i].update(updates)
                break
    
    def update_outbound_record_in_db(self, record_id: int, updates: Dict):
        """출고 기록 수정 (Supabase)"""
        self.supabase.table('outbound_records')\
            .update(updates)\
            .eq('id', record_id)\
            .execute()
        
        # 메모리 업데이트
        for i, r in enumerate(self.outbound_records):
            if r['id'] == record_id:
                self.outbound_records[i].update(updates)
                break
    
    def update_movement_in_db(self, movement_id: int, updates: Dict):
        """재고 이동 수정 (Supabase)"""
        # notes 필드명 변환
        db_updates = {**updates}
        if 'note' in db_updates:
            db_updates['notes'] = db_updates.pop('note')
        
        self.supabase.table('inventory_movements')\
            .update(db_updates)\
            .eq('id', movement_id)\
            .execute()
        
        # 메모리 업데이트
        for i, m in enumerate(self.movements):
            if m['id'] == movement_id:
                self.movements[i].update(updates)
                break
    
    def reload_from_db(self):
        """Supabase에서 데이터 다시 로드"""
        return self.load_data()
    
    def delete_inbound_record_from_db(self, record_id: int):
        """입고 기록 삭제 (Supabase)"""
        self.supabase.table('inbound_records')\
            .delete()\
            .eq('id', record_id)\
            .execute()
        self.inbound_records = [r for r in self.inbound_records if r['id'] != record_id]
    
    def delete_outbound_record_from_db(self, record_id: int):
        """출고 기록 삭제 (Supabase)"""
        self.supabase.table('outbound_records')\
            .delete()\
            .eq('id', record_id)\
            .execute()
        self.outbound_records = [r for r in self.outbound_records if r['id'] != record_id]
    
    def delete_movement_from_db(self, movement_id: int):
        """재고 이동 삭제 (Supabase)"""
        self.supabase.table('inventory_movements')\
            .delete()\
            .eq('id', movement_id)\
            .execute()
        self.movements = [m for m in self.movements if m['id'] != movement_id]
    
    def add_store_to_db(self, store: Dict) -> Dict:
        """매장 추가 (Supabase)"""
        db_store = {
            'organization_id': self.organization_id,
            'name': store['name'],
            'address': store.get('address', '')
        }
        response = self.supabase.table('stores').insert(db_store).execute()
        new_store = response.data[0]
        self.stores.append(new_store)
        return new_store
    
    def delete_store_from_db(self, store_id: int):
        """매장 삭제 (Supabase)"""
        self.supabase.table('stores')\
            .delete()\
            .eq('id', store_id)\
            .execute()
        self.stores = [s for s in self.stores if s['id'] != store_id]
