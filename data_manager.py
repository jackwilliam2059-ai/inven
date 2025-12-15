"""
DataManager class for handling all data operations
Manages data loading, saving, cloud sync, backups, locks, and Excel operations
"""

import json
import os
from datetime import datetime
from tkinter import messagebox
import utils


class DataManager:
    """Handles all data operations including load, save, backup, and lock management"""

    def __init__(self, config_file="cloud_config.json"):
        """Initialize DataManager with configuration"""
        self.config_file = config_file
        self.settings_file = "app_settings.json"

        # Load cloud configuration
        self.cloud_info = self.load_cloud_path()
        self.cloud_path = self.cloud_info.get('path', '')
        self.cloud_type = self.cloud_info.get('type', 'local')

        # Set data file paths (cloud or local)
        if self.cloud_path and os.path.exists(self.cloud_path):
            self.data_file = os.path.join(self.cloud_path, "inventory_data.json")
            self.lock_file = os.path.join(self.cloud_path, "inventory_lock.json")
            self.users_file = os.path.join(self.cloud_path, "inventory_users.json")
            self.settings_file = os.path.join(self.cloud_path, "app_settings.json")
        else:
            self.data_file = "inventory_data.json"
            self.lock_file = "inventory_lock.json"
            self.users_file = "inventory_users.json"
            self.settings_file = "app_settings.json"

        # Data containers
        self.products = []
        self.orders = []
        self.movements = []
        self.inbound_records = []
        self.outbound_records = []
        self.stores = []
        self.field_names = []
        self.settlement_balances = {}  # 출고장 정산 잔액 관리 {store_id: balance}

        # User info
        self.current_user = utils.get_current_user()
        self.user_display_name = os.environ.get('USERNAME', os.environ.get('USER', '사용자'))
        self.is_locked = False

        # Load app settings
        self.app_settings = self.load_app_settings()

    def load_cloud_path(self):
        """클라우드 경로 로드"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass

        # 자동으로 클라우드 경로 찾기
        return utils.auto_detect_cloud()

    def save_cloud_path(self, path, cloud_type):
        """클라우드 경로 저장"""
        try:
            config = {
                'path': path,
                'type': cloud_type,
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showerror("오류", f"설정 저장 중 오류가 발생했습니다:\n{str(e)}")

    def load_users_config(self):
        """사용자 설정 로드"""
        if os.path.exists(self.users_file):
            try:
                with open(self.users_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def save_users_config(self, users_config):
        """사용자 설정 저장"""
        try:
            with open(self.users_file, 'w', encoding='utf-8') as f:
                json.dump(users_config, f, ensure_ascii=False, indent=2)
        except:
            pass

    def load_app_settings(self):
        """앱 설정 로드"""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        # 기본 설정
        return {
            'auto_split_product_code': False  # 상품코드 자동 분리 기본값: False
        }

    def save_app_settings(self, settings):
        """앱 설정 저장"""
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            self.app_settings = settings
        except Exception as e:
            messagebox.showerror("오류", f"설정 저장 중 오류가 발생했습니다:\n{str(e)}")

    def get_auto_split_setting(self):
        """상품코드 자동 분리 설정 가져오기"""
        return self.app_settings.get('auto_split_product_code', False)

    def set_auto_split_setting(self, value):
        """상품코드 자동 분리 설정 저장"""
        self.app_settings['auto_split_product_code'] = value
        self.save_app_settings(self.app_settings)

    def check_lock(self):
        """다른 사용자가 사용 중인지 확인"""
        if not os.path.exists(self.lock_file):
            return False, None

        try:
            with open(self.lock_file, 'r', encoding='utf-8') as f:
                lock_data = json.load(f)

            # 잠금 시간 확인 (30초 이상 응답 없으면 무효)
            lock_time = datetime.strptime(lock_data['timestamp'], '%Y-%m-%d %H:%M:%S')
            if (datetime.now() - lock_time).seconds > 30:
                return False, None

            # 자신의 잠금인지 확인
            if lock_data['user'] == self.current_user:
                return False, None

            return True, lock_data['display_name']
        except:
            return False, None

    def acquire_lock(self):
        """잠금 획득"""
        try:
            lock_data = {
                'user': self.current_user,
                'display_name': self.user_display_name,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            with open(self.lock_file, 'w', encoding='utf-8') as f:
                json.dump(lock_data, f, ensure_ascii=False, indent=2)
            self.is_locked = True
            return True
        except Exception as e:
            messagebox.showerror("오류", f"잠금을 획득할 수 없습니다:\n{str(e)}")
            return False

    def release_lock(self):
        """잠금 해제"""
        try:
            if os.path.exists(self.lock_file):
                with open(self.lock_file, 'r', encoding='utf-8') as f:
                    lock_data = json.load(f)

                # 자신의 잠금인 경우만 해제
                if lock_data['user'] == self.current_user:
                    os.remove(self.lock_file)
            self.is_locked = False
        except:
            pass

    def update_lock(self):
        """잠금 갱신 (살아있음을 알림)"""
        if self.is_locked:
            try:
                lock_data = {
                    'user': self.current_user,
                    'display_name': self.user_display_name,
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                with open(self.lock_file, 'w', encoding='utf-8') as f:
                    json.dump(lock_data, f, ensure_ascii=False, indent=2)
            except:
                pass

    def auto_backup_data(self):
        """프로그램 종료 시 자동 백업 (최대 30개 유지)"""
        # 클라우드 경로가 설정되지 않았으면 백업하지 않음
        if not self.cloud_path or not os.path.exists(self.cloud_path):
            return

        try:
            # 백업 폴더 경로 설정
            backup_folder = os.path.join(self.cloud_path, "auto_backups")
            if not os.path.exists(backup_folder):
                os.makedirs(backup_folder)

            # 현재 데이터를 백업 파일로 저장
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"inventory_backup_{timestamp}.json"
            backup_filepath = os.path.join(backup_folder, backup_filename)

            # 데이터 준비
            data = {
                'products': self.products,
                'orders': self.orders,
                'movements': self.movements,
                'inbound_records': self.inbound_records,
                'outbound_records': self.outbound_records,
                'stores': self.stores,
                'settlement_balances': self.settlement_balances,
                'field_names': self.field_names,
                'last_saved': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'last_saved_by': self.user_display_name,
                'cloud_type': self.cloud_type
            }

            # 백업 파일 저장
            with open(backup_filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # 백업 파일 개수 확인 및 오래된 파일 삭제 (30개 초과 시)
            backup_files = sorted([f for f in os.listdir(backup_folder)
                                 if f.startswith('inventory_backup_') and f.endswith('.json')])

            while len(backup_files) > 30:
                oldest_file = backup_files.pop(0)
                os.remove(os.path.join(backup_folder, oldest_file))
                print(f"오래된 백업 파일 삭제: {oldest_file}")

            print(f"자동 백업 완료: {backup_filename}")

        except Exception as e:
            print(f"자동 백업 중 오류: {str(e)}")

    def check_and_restore_backup(self):
        """프로그램 시작 시 최신 백업과 현재 데이터 비교 후 복원"""
        # 클라우드 경로가 설정되지 않았으면 체크하지 않음
        if not self.cloud_path or not os.path.exists(self.cloud_path):
            return None

        backup_folder = os.path.join(self.cloud_path, "auto_backups")
        if not os.path.exists(backup_folder):
            return None

        try:
            # 백업 파일 목록 가져오기 (최신순)
            backup_files = sorted([f for f in os.listdir(backup_folder)
                                 if f.startswith('inventory_backup_') and f.endswith('.json')],
                                reverse=True)

            if not backup_files:
                return None

            # 최신 백업 파일
            latest_backup = os.path.join(backup_folder, backup_files[0])

            # 현재 데이터 파일이 없으면 백업에서 복원 여부 반환
            if not os.path.exists(self.data_file):
                return {'type': 'no_current', 'backup_file': latest_backup, 'backup_name': backup_files[0]}

            # 현재 데이터 파일과 백업 파일의 수정 시간 비교
            current_mtime = os.path.getmtime(self.data_file)
            backup_mtime = os.path.getmtime(latest_backup)

            # 백업이 더 최신인 경우에만 반환
            if backup_mtime > current_mtime:
                # 백업 파일의 저장 시간 정보 읽기
                with open(latest_backup, 'r', encoding='utf-8') as f:
                    backup_data = json.load(f)

                backup_time = backup_data.get('last_saved', '알 수 없음')
                backup_user = backup_data.get('last_saved_by', '알 수 없음')

                # 현재 파일의 저장 시간 정보 읽기
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    current_data = json.load(f)

                current_time = current_data.get('last_saved', '알 수 없음')
                current_user = current_data.get('last_saved_by', '알 수 없음')

                return {
                    'type': 'newer_backup',
                    'backup_file': latest_backup,
                    'backup_time': backup_time,
                    'backup_user': backup_user,
                    'current_time': current_time,
                    'current_user': current_user,
                    'backup_data': backup_data
                }

        except Exception as e:
            print(f"백업 확인 중 오류: {str(e)}")
            return None

        return None

    def restore_from_backup(self, backup_data):
        """백업 데이터로부터 복원"""
        self.products = backup_data.get('products', [])
        for product in self.products:
            try:
                product['id'] = int(product.get('id', 0))
            except (ValueError, TypeError):
                product['id'] = 0

        self.orders = backup_data.get('orders', [])
        self.movements = backup_data.get('movements', [])
        self.inbound_records = backup_data.get('inbound_records', [])
        self.outbound_records = backup_data.get('outbound_records', [])
        self.stores = backup_data.get('stores', [])
        self.field_names = backup_data.get('field_names', [
            {'id': 'field1', 'name': '색상'},
            {'id': 'field2', 'name': '사이즈'}
        ])

        # 복원된 데이터를 현재 데이터 파일로 저장
        self.save_data()

    def load_data(self):
        """데이터 파일 로드"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.products = data.get('products', [])

                    # ID를 정수로 변환 (문자열과 숫자 혼재 문제 해결)
                    for product in self.products:
                        try:
                            product['id'] = int(product.get('id', 0))
                        except (ValueError, TypeError):
                            product['id'] = 0

                    self.orders = data.get('orders', [])
                    self.movements = data.get('movements', [])
                    self.inbound_records = data.get('inbound_records', [])
                    self.outbound_records = data.get('outbound_records', [])
                    self.stores = data.get('stores', [])
                    self.settlement_balances = data.get('settlement_balances', {})

                    # 필드명 로드 (기존 형식 호환)
                    loaded_fields = data.get('field_names')
                    if loaded_fields:
                        if isinstance(loaded_fields, dict):
                            # 구 형식: dict -> list로 변환
                            self.field_names = [
                                {'id': 'field1', 'name': loaded_fields.get('color', '색상')},
                                {'id': 'field2', 'name': loaded_fields.get('size', '사이즈')}
                            ]
                        elif isinstance(loaded_fields, list):
                            # 신 형식
                            self.field_names = loaded_fields
                    else:
                        # 기본값
                        self.field_names = [
                            {'id': 'field1', 'name': '색상'},
                            {'id': 'field2', 'name': '사이즈'}
                        ]

                    # 마지막 저장 정보 표시
                    last_saved = data.get('last_saved')
                    last_saved_by = data.get('last_saved_by')
                    if last_saved and last_saved_by:
                        print(f"마지막 저장: {last_saved} by {last_saved_by}")

                    return True
            except Exception as e:
                messagebox.showerror("오류", f"데이터 로드 중 오류가 발생했습니다:\n{str(e)}")
                # 오류 시 기본값
                self.field_names = [
                    {'id': 'field1', 'name': '색상'},
                    {'id': 'field2', 'name': '사이즈'}
                ]
                return False
        else:
            # 데이터 파일이 없으면 기본값
            self.field_names = [
                {'id': 'field1', 'name': '색상'},
                {'id': 'field2', 'name': '사이즈'}
            ]
            # 클라우드 경로 안내
            if self.cloud_path and not os.path.exists(self.data_file):
                messagebox.showinfo("안내",
                    f"{self.cloud_type} 경로에 데이터 파일이 없습니다.\n"
                    f"새로운 데이터 파일을 생성합니다.\n\n"
                    f"위치: {self.data_file}")
            return False

    def save_data(self):
        """데이터 파일 저장"""
        try:
            # 클라우드 경로가 설정되어 있지만 폴더가 없으면 생성
            if self.cloud_path and not os.path.exists(self.cloud_path):
                try:
                    os.makedirs(self.cloud_path, exist_ok=True)
                except:
                    messagebox.showerror("오류",
                        f"클라우드 폴더를 생성할 수 없습니다:\n{self.cloud_path}\n\n"
                        f"로컬 폴더에 저장합니다.")
                    self.data_file = "inventory_data.json"

            data = {
                'products': self.products,
                'orders': self.orders,
                'movements': self.movements,
                'inbound_records': self.inbound_records,
                'outbound_records': self.outbound_records,
                'stores': self.stores,
                'settlement_balances': self.settlement_balances,
                'field_names': self.field_names,
                'last_saved': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'last_saved_by': self.user_display_name,
                'cloud_type': self.cloud_type
            }
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            return True
        except Exception as e:
            messagebox.showerror("오류", f"데이터 저장 중 오류가 발생했습니다:\n{str(e)}")
            # 오류 발생 시 로컬에 백업 저장 시도
            try:
                backup_file = "inventory_data_backup.json"
                with open(backup_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                messagebox.showinfo("백업 저장", f"원본 저장 실패로 백업 파일에 저장했습니다:\n{backup_file}")
            except:
                pass
            return False

    def get_product_by_id(self, product_id):
        """ID로 상품 찾기"""
        for p in self.products:
            if str(p['id']) == str(product_id):
                return p

        # 디버깅: 찾지 못한 경우
        print(f"⚠️ product_id '{product_id}' (타입: {type(product_id)})를 찾을 수 없습니다.")
        if self.products:
            print(f"   현재 상품 예시: ID={self.products[0]['id']} (타입: {type(self.products[0]['id'])}), 이름={self.products[0]['name']}")
        return None

    def get_store_by_id(self, store_id):
        """ID로 매장 찾기"""
        for s in self.stores:
            if s['id'] == store_id:
                return s
        return None

    def get_next_product_id(self):
        """다음 상품 ID 생성 (기존 ID 중 최대값 + 1, 중복 방지)"""
        if not self.products:
            return 1

        # 사용 중인 모든 ID 수집
        used_ids = set()
        for product in self.products:
            try:
                product_id = int(product.get('id', 0))
                used_ids.add(product_id)
            except (ValueError, TypeError):
                continue

        # 최대 ID 찾기
        max_id = max(used_ids) if used_ids else 0

        # 최대 ID + 1부터 시작하여 사용되지 않은 ID 찾기
        next_id = max_id + 1
        while next_id in used_ids:
            next_id += 1

        return next_id

    def check_and_fix_duplicate_ids(self):
        """ID 충돌을 검사하고 자동으로 수정 (저장 안 함!)
        
        Returns:
            int: 수정된 상품 개수
        """
        from collections import Counter
        
        # 모든 상품 ID 수집
        ids = []
        for product in self.products:
            try:
                product_id = int(product.get('id', 0))
                ids.append(product_id)
            except (ValueError, TypeError):
                continue
        
        # 중복 ID 찾기
        id_counts = Counter(ids)
        duplicates = {id_num: count for id_num, count in id_counts.items() if count > 1}
        
        if not duplicates:
            return 0  # 중복 없음
        
        # ID 매핑 테이블
        fixed_count = 0
        used_ids = set(ids)
        
        # 각 중복 ID 처리
        for dup_id in sorted(duplicates.keys()):
            # 해당 ID를 가진 상품들 찾기
            conflicting_products = [p for p in self.products if p.get('id') == dup_id]
            
            # 첫 번째는 유지, 나머지는 새 ID 배정
            for idx, product in enumerate(conflicting_products):
                if idx == 0:
                    continue  # 첫 번째는 그대로
                
                # 새 ID 배정
                new_id = max(used_ids) + 1
                while new_id in used_ids:
                    new_id += 1
                
                old_id = product['id']
                product['id'] = new_id
                used_ids.add(new_id)
                
                # 관련 거래 데이터 업데이트
                for order in self.orders:
                    if order.get('product_id') == old_id:
                        order['product_id'] = new_id
                
                for record in self.inbound_records:
                    if record.get('product_id') == old_id:
                        record['product_id'] = new_id
                
                for record in self.outbound_records:
                    if record.get('product_id') == old_id:
                        record['product_id'] = new_id
                
                for movement in self.movements:
                    if movement.get('product_id') == old_id:
                        movement['product_id'] = new_id
                
                fixed_count += 1
        
        # 주의: 저장하지 않음! 사용자가 수동으로 저장해야 함
        return fixed_count

    def calculate_stock(self, product_id):
        """재고 계산 (입고 - 출고)"""
        received = sum(m['quantity'] for m in self.movements if m['product_id'] == product_id and m['type'] == 'in')
        shipped = sum(m['quantity'] for m in self.movements if m['product_id'] == product_id and m['type'] == 'out')
        return received - shipped

    def calculate_stock_by_variant(self, product_id, color, size):
        """색상/사이즈별 재고 계산"""
        received = sum(m['quantity'] for m in self.movements
                      if m['product_id'] == product_id and m['type'] == 'in'
                      and m.get('color', '') == color and m.get('size', 'FREE') == size)
        shipped = sum(m['quantity'] for m in self.movements
                     if m['product_id'] == product_id and m['type'] == 'out'
                     and m.get('color', '') == color and m.get('size', 'FREE') == size)
        return received - shipped

    def calculate_pending(self, product_id):
        """미입고 수량 계산"""
        total = 0
        for o in self.orders:
            if o['product_id'] == product_id and o.get('status') != 'completed':
                total += (o['quantity'] - o['shipped_quantity'])
        return total

    def calculate_pending_by_variant(self, product_id, color, size):
        """색상/사이즈별 미입고 수량 계산"""
        total = 0
        for o in self.orders:
            if (o['product_id'] == product_id and o.get('status') != 'completed'
                and o.get('color', '') == color and o.get('size', 'FREE') == size):
                total += (o['quantity'] - o['shipped_quantity'])
        return total

    # ========== Supabase 호환 메서드 (JSON 모드에서는 save_data 호출) ==========
    
    def update_order_in_db(self, order_id, data):
        """발주 업데이트 (JSON 모드: 메모리에서 이미 수정됨, save_data는 수동 저장)"""
        pass  # 메모리에서 이미 수정되었으므로 별도 작업 불필요
    
    def update_inbound_record_in_db(self, record_id, data):
        """입고 기록 업데이트 (JSON 모드)"""
        pass
    
    def update_outbound_record_in_db(self, record_id, data):
        """출고 기록 업데이트 (JSON 모드)"""
        pass
    
    def update_movement_in_db(self, movement_id, data):
        """재고이동 업데이트 (JSON 모드)"""
        pass
    
    def update_product_in_db(self, product_id, data):
        """상품 업데이트 (JSON 모드)"""
        pass
