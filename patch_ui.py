#!/usr/bin/env python3
"""
재고관리 프로그램 UI 편의성 자동 패치 스크립트
main_fixed.py를 main_enhanced.py로 변환
"""

import sys
import re

def patch_main_file(input_file, output_file):
    """main_fixed.py에 UI 개선 패치 적용"""
    
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print("✅ 파일 로드 완료")
    
    # 1. import 추가
    if 'from tkinter import simpledialog' not in content:
        content = content.replace(
            'from tkinter import ttk, messagebox, filedialog',
            'from tkinter import ttk, messagebox, filedialog, simpledialog'
        )
        print("✅ 1. simpledialog import 추가")
    
    # 2. 상품관리탭 더블클릭 바인딩 변경
    content = content.replace(
        'self.products_tree.bind("<Double-1>", self.show_product_detail)',
        'self.products_tree.bind("<Double-1>", self.on_products_tree_double_click)'
    )
    print("✅ 2. 상품관리탭 바인딩 변경")
    
    # 3. 발주관리탭 더블클릭 바인딩 추가
    # orders_tree 생성 부분 찾기
    pattern = r'(self\.orders_tree = ttk\.Treeview\([^)]+\))'
    match = re.search(pattern, content)
    if match:
        # orders_tree 생성 이후에 바인딩 추가
        insert_pos = content.find('\n', match.end()) + 1
        if 'self.orders_tree.bind("<Double-1>"' not in content[insert_pos:insert_pos+500]:
            binding = '        self.orders_tree.bind("<Double-1>", self.on_orders_tree_double_click)\n'
            content = content[:insert_pos] + binding + content[insert_pos:]
            print("✅ 3. 발주관리탭 바인딩 추가")
    
    # 4. 셀 편집 함수들 추가
    # manual_save 함수 다음에 추가
    insert_marker = '    def refresh_with_merge(self):'
    if insert_marker in content:
        insert_pos = content.find(insert_marker)
        
        new_functions = '''    def on_products_tree_double_click(self, event):
        """상품관리탭 더블클릭 시 셀 편집"""
        region = self.products_tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        
        column = self.products_tree.identify_column(event.x)
        col_index = int(column.replace('#', '')) - 1
        columns = self.products_tree['columns']
        col_name = columns[col_index]
        
        item_id = self.products_tree.identify_row(event.y)
        if not item_id:
            return
        
        # 편집 가능한 열만 허용
        editable_columns = ['상품코드', '상품명', '매입처']
        if col_name not in editable_columns:
            self.show_product_detail(event)
            return
        
        values = self.products_tree.item(item_id)['values']
        current_value = values[col_index]
        
        new_value = simpledialog.askstring(f"{col_name} 수정", 
                                           f"새로운 {col_name}:",
                                           initialvalue=str(current_value))
        if new_value is None:
            return
        
        product_name = values[0]
        product_code = values[1]
        
        for p in self.products:
            if p['name'] == product_name and p.get('code', '') == product_code:
                if col_name == '상품코드':
                    p['code'] = new_value
                elif col_name == '상품명':
                    p['name'] = new_value
                elif col_name == '매입처':
                    p['supplier'] = new_value
                break
        
        self.refresh_products_list()
        messagebox.showinfo("수정 완료", "⚠️ 💾 저장 버튼을 눌러 변경사항을 저장하세요!")
    
    def on_orders_tree_double_click(self, event):
        """발주관리탭 더블클릭 시 수량 편집"""
        region = self.orders_tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        
        column = self.orders_tree.identify_column(event.x)
        col_index = int(column.replace('#', '')) - 1
        columns = self.orders_tree['columns']
        col_name = columns[col_index]
        
        if col_name not in ['발주수량', '출고수량']:
            return
        
        item_id = self.orders_tree.identify_row(event.y)
        if not item_id:
            return
        
        values = self.orders_tree.item(item_id)['values']
        current_value = values[col_index]
        
        new_value = simpledialog.askinteger(f"{col_name} 수정",
                                            f"새로운 {col_name}:",
                                            initialvalue=int(current_value))
        if new_value is None:
            return
        
        order_date = values[0]
        product_name = values[1]
        color = values[3] if values[3] != '-' else ''
        size = values[4]
        store_name = values[5] if values[5] != '-' else ''
        
        store_id = ''
        for s in self.stores:
            if s['name'] == store_name:
                store_id = s.get('id', '')
                break
        
        product = None
        for p in self.products:
            if p['name'] == product_name:
                product_colors = p.get('colors', [''])
                if not color or color in product_colors:
                    product = p
                    break
        
        if not product:
            return
        
        for order in self.orders:
            if (order['product_id'] == product['id'] and
                order['date'] == order_date and
                order.get('color', '') == color and
                order.get('size', 'FREE') == size and
                order.get('store_id', '') == store_id):
                
                if col_name == '발주수량':
                    order['quantity'] = new_value
                elif col_name == '출고수량':
                    order['shipped_quantity'] = new_value
                break
        
        self.refresh_orders_list()
        messagebox.showinfo("수정 완료", "⚠️ 💾 저장 버튼을 눌러 변경사항을 저장하세요!")
    
'''
        
        if 'def on_products_tree_double_click' not in content:
            content = content[:insert_pos] + new_functions + content[insert_pos:]
            print("✅ 4. 셀 편집 함수들 추가")
    
    # 5. 발주 시 메모 기능 추가는 복잡하므로 별도로 수동 수정 필요
    print("⚠️  5. 발주 메모 기능은 수동 수정 필요 (가이드 참조)")
    
    # 6. 엑셀 출력 시 미입고현황 → 메모로 변경
    content = content.replace(
        "headers = ['발주일자', '상품명', '상품코드', '색상', '사이즈', '발주수량', '출고수량', '미출고', '매장', '미입고현황']",
        "headers = ['발주일자', '상품명', '상품코드', '색상', '사이즈', '발주수량', '출고수량', '미출고', '매장', '메모']"
    )
    
    # pending_summary를 메모로 변경
    content = re.sub(
        r'pending_summary = f"{pending_total}장"',
        'order_note = order.get("note", "")',
        content
    )
    
    content = content.replace(
        '            pending_summary\n        ]',
        '            order_note\n        ]'
    )
    
    print("✅ 6. 엑셀 출력 헤더 및 데이터 수정")
    
    # 저장
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"\n✅ 패치 완료!")
    print(f"입력: {input_file}")
    print(f"출력: {output_file}")
    print("\n⚠️  주의: 발주 메모 기능은 UI개선_간단가이드.md를 참조하여 수동 추가 필요")

if __name__ == '__main__':
    input_file = 'main_fixed.py'
    output_file = 'main_enhanced.py'
    
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
    if len(sys.argv) > 2:
        output_file = sys.argv[2]
    
    try:
        patch_main_file(input_file, output_file)
    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
