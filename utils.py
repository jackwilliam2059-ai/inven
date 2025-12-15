"""
Independent utility functions for the Inventory Management System
These functions don't rely on the class structure and can be used standalone
"""

import tkinter as tk
from tkinter import messagebox
import os
import platform
import socket
import base64
from io import BytesIO
import urllib.request
import re
import difflib


def get_current_user():
    """현재 사용자 정보 가져오기"""
    try:
        computer_name = socket.gethostname()
        user_name = os.environ.get('USERNAME', os.environ.get('USER', 'Unknown'))
        return f"{user_name}@{computer_name}"
    except:
        return "Unknown User"


def center_window(window):
    """창을 화면 중앙에 배치"""
    window.update_idletasks()
    width = window.winfo_width()
    height = window.winfo_height()
    x = (window.winfo_screenwidth() // 2) - (width // 2)
    y = (window.winfo_screenheight() // 2) - (height // 2)
    window.geometry(f'{width}x{height}+{x}+{y}')


def download_image_from_url(image_url):
    """URL에서 이미지 다운로드 및 Base64 인코딩"""
    try:
        if not image_url or not image_url.startswith('http'):
            return None

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://www.dearwith.com/'
        }
        req = urllib.request.Request(image_url, headers=headers)

        with urllib.request.urlopen(req, timeout=15) as response:
            img_data = response.read()

        # 이미지 크기 확인 (최소 크기 제약)
        if len(img_data) < 1000:  # 1KB 미만이면 무시
            return None

        # 유효한 이미지인지 확인
        try:
            from PIL import Image
            Image.open(BytesIO(img_data))
        except:
            return None

        # Base64로 인코딩
        image_base64 = base64.b64encode(img_data).decode()
        return image_base64

    except Exception as e:
        print(f"이미지 다운로드 오류: {str(e)}")
        return None


def get_image_from_clipboard_or_url():
    """클립보드에서 이미지 URL 가져오기"""
    try:
        root = tk.Tk()
        root.withdraw()
        clipboard_content = root.clipboard_get()
        root.destroy()

        # URL인지 확인
        if clipboard_content.startswith('http') and any(ext in clipboard_content.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
            return clipboard_content
        return None
    except:
        return None


def extract_similar_products(html_content, search_name):
    """HTML에서 비슷한 상품명 추출"""
    # 정규표현식으로 상품명 패턴 찾기
    patterns = [
        r'<span[^>]*class="product-name"[^>]*>([^<]+)</span>',
        r'<a[^>]*title="([^"]{5,})"[^>]*class="product',
        r'<h3[^>]*class="product-title"[^>]*>([^<]{5,})</h3>',
        r'<div[^>]*class="product-title"[^>]*>([^<]{5,})</div>',
        r'alt="([^"]{5,})"[^>]*src="[^"]*(?:jpg|png|jpeg)"'
    ]

    found_names = set()
    for pattern in patterns:
        try:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            found_names.update([m.strip() for m in matches])
        except:
            continue

    # 비슷한 상품명 찾기
    similar = []
    search_name_lower = search_name.lower()

    for name in found_names:
        name_lower = name.lower().strip()
        if name_lower and len(name_lower) > 3 and len(name_lower) < 100:
            ratio = difflib.SequenceMatcher(None, search_name_lower, name_lower).ratio()
            if ratio >= 0.4:  # 40% 이상 유사
                similar.append((name, ratio))

    # 유사도 순으로 정렬
    similar.sort(key=lambda x: x[1], reverse=True)
    return [name for name, _ in similar[:5]]


def search_dearwith_image_selenium(product_name):
    """Selenium을 사용하여 일반 이용자처럼 Dearwith.com에서 이미지 검색"""
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.chrome.options import Options
        import time

        # Chrome 옵션 설정
        chrome_options = Options()
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        # WebDriver 생성
        driver = webdriver.Chrome(options=chrome_options)

        try:
            print(f"🔍 Dearwith에서 '{product_name}' 검색 중...")

            # 검색 페이지 접속
            search_url = f"https://www.dearwith.com/search?keyword={product_name}"
            driver.get(search_url)
            time.sleep(3)

            # 페이지 소스 가져오기
            page_source = driver.page_source

            # 비슷한 상품명 추출
            similar_products = extract_similar_products(page_source, product_name)

            # 이미지 요소 찾기
            image_selectors = [
                "img.product-image",
                "img.product-thumb",
                "div.product-item img",
                "a.product-link img",
                "img[alt*='product']",
                "img[src*='product']"
            ]

            images = []
            for selector in image_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for elem in elements:
                        src = elem.get_attribute("src")
                        if src and any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                            images.append(src)
                except:
                    continue

            if images:
                img_url = images[0]
                if img_url.startswith('/'):
                    img_url = f"https://www.dearwith.com{img_url}"
                elif not img_url.startswith('http'):
                    img_url = f"https://www.dearwith.com/{img_url}"

                # 비슷한 상품명이 있으면 사용자에게 확인
                if similar_products:
                    similar_text = '\n'.join([f"• {name}" for name in similar_products[:5]])
                    result = messagebox.askyesno(
                        "유사 상품 발견",
                        f"'{product_name}'과(와) 비슷한 상품들:\n\n{similar_text}\n\n"
                        f"검색된 이미지를 사용하시겠습니까?"
                    )
                    if not result:
                        return None

                return img_url
            else:
                return None

        finally:
            driver.quit()

    except ImportError:
        messagebox.showwarning(
            "경고",
            "Selenium이 설치되어 있지 않습니다.\n\n"
            "자동 이미지 검색을 사용하려면:\n"
            "명령 프롬프트에서 'pip install selenium' 입력"
        )
        return None
    except Exception as e:
        print(f"Selenium 검색 오류: {str(e)}")
        return None


def search_dearwith_image(product_name):
    """Dearwith.com에서 상품 이미지 검색 (Selenium 사용)"""
    # Selenium이 설치되어 있으면 사용, 아니면 None 반환
    return search_dearwith_image_selenium(product_name)


def auto_detect_cloud():
    """클라우드 스토리지 경로 자동 감지"""
    detected_clouds = []

    if platform.system() == 'Windows':
        user_profile = os.environ.get('USERPROFILE', '')

        # 원드라이브 경로들
        onedrive_paths = [
            (os.path.join(user_profile, 'OneDrive'), 'OneDrive'),
            (os.path.join(user_profile, 'OneDrive - Personal'), 'OneDrive'),
            (os.path.join(user_profile, 'OneDrive - 비즈니스'), 'OneDrive Business'),
        ]

        # 구글 드라이브 경로들
        google_drive_paths = [
            (os.path.join(user_profile, 'Google Drive'), 'Google Drive'),
            (os.path.join(user_profile, 'Google 드라이브'), 'Google Drive'),
            ('G:\\내 드라이브', 'Google Drive'),
            ('G:\\My Drive', 'Google Drive'),
        ]

        # 드롭박스 경로들
        dropbox_paths = [
            (os.path.join(user_profile, 'Dropbox'), 'Dropbox'),
        ]

        # 네이버 클라우드 경로들
        naver_paths = [
            (os.path.join(user_profile, 'NAVER Cloud'), 'Naver Cloud'),
            (os.path.join(user_profile, '네이버 클라우드'), 'Naver Cloud'),
        ]

        # iCloud Drive 경로들
        icloud_paths = [
            (os.path.join(user_profile, 'iCloudDrive'), 'iCloud Drive'),
        ]

        all_paths = onedrive_paths + google_drive_paths + dropbox_paths + naver_paths + icloud_paths

        for path, cloud_type in all_paths:
            if os.path.exists(path):
                detected_clouds.append({'path': path, 'type': cloud_type})

    # 첫 번째로 발견된 클라우드 반환
    if detected_clouds:
        return detected_clouds[0]

    return {'path': '', 'type': 'local'}


def make_scrollable_dialog(dialog, max_height=None):
    """
    Toplevel 다이얼로그에 스크롤바를 추가하는 유틸리티 함수

    Args:
        dialog: tk.Toplevel 객체
        max_height: 최대 높이 (픽셀). None이면 화면 높이의 80%

    Returns:
        content_frame: 실제 컨텐츠를 넣을 프레임
    """
    from tkinter import ttk

    # 최대 높이 설정
    if max_height is None:
        screen_height = dialog.winfo_screenheight()
        max_height = int(screen_height * 0.8)

    # 메인 프레임 생성
    main_frame = tk.Frame(dialog)
    main_frame.pack(fill=tk.BOTH, expand=True)

    # Canvas 및 스크롤바 생성
    canvas = tk.Canvas(main_frame)
    scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)

    # 스크롤 가능한 프레임
    scrollable_frame = tk.Frame(canvas)
    
    # 중앙 정렬을 위한 wrapper 추가
    center_wrapper = tk.Frame(scrollable_frame)
    center_wrapper.pack(fill='x', expand=True)
    center_wrapper.columnconfigure(0, weight=1)  # 왼쪽 공간
    center_wrapper.columnconfigure(1, weight=0)  # 중앙 컨텐츠
    center_wrapper.columnconfigure(2, weight=1)  # 오른쪽 공간
    
    # 실제 컨텐츠가 들어갈 프레임
    content_container = tk.Frame(center_wrapper)
    content_container.grid(row=0, column=1, sticky='n')

    # 프레임 크기 변경 시 스크롤 영역 업데이트
    def on_frame_configure(event):
        canvas.configure(scrollregion=canvas.bbox("all"))

        # 내용이 max_height보다 크면 스크롤바 표시
        if scrollable_frame.winfo_reqheight() > max_height:
            scrollbar.pack(side="right", fill="y")
            dialog.geometry(f"{dialog.winfo_reqwidth()}x{max_height}")
        else:
            # 스크롤바가 필요없으면 숨김
            scrollbar.pack_forget()

    scrollable_frame.bind("<Configure>", on_frame_configure)

    # Canvas에 프레임 추가
    window_id = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    # Canvas 배치
    canvas.pack(side="left", fill=tk.BOTH, expand=True)
    
    # Canvas 너비에 맞춰 scrollable_frame 너비 조정
    def on_canvas_configure(event):
        canvas.itemconfig(window_id, width=event.width)
    
    canvas.bind("<Configure>", on_canvas_configure)

    # 마우스 휠 스크롤 지원
    def on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    canvas.bind_all("<MouseWheel>", on_mousewheel)

    return content_container


def auto_split_product_code(product_code):
    """
    상품코드에서 색상과 사이즈를 자동으로 분리

    Args:
        product_code: 상품코드 문자열 (예: "TOP-RED-L", "SHIRT_BLUE_M")

    Returns:
        tuple: (색상 리스트, 사이즈 리스트)
    """
    if not product_code or not isinstance(product_code, str):
        return ([], [])

    # 상품코드를 구분자로 분리 (-, _, 공백 등)
    parts = re.split(r'[-_\s/]+', product_code.strip())

    # 알려진 색상 패턴
    color_patterns = [
        # 한글 색상
        r'빨강|레드|적색',
        r'파랑|블루|청색',
        r'초록|그린|녹색',
        r'노랑|옐로우|황색',
        r'검정|블랙|흑색',
        r'하양|화이트|백색',
        r'회색|그레이',
        r'보라|퍼플|자주|바이올렛',
        r'분홍|핑크',
        r'주황|오렌지',
        r'갈색|브라운',
        r'베이지',
        r'네이비|남색',
        r'카키',
        r'민트',
        r'라벤더|연보라',
        r'코랄|산호',
        r'아이보리',
        r'크림',
        # 영어 색상
        r'red', r'blue', r'green', r'yellow', r'black', r'white',
        r'gray|grey', r'purple', r'pink', r'orange', r'brown',
        r'beige', r'navy', r'khaki', r'mint', r'lavender',
        r'coral', r'ivory', r'cream', r'violet'
    ]

    # 알려진 사이즈 패턴
    size_patterns = [
        r'^(XS|S|M|L|XL|XXL|XXXL|2XL|3XL)$',
        r'^[0-9]{2,3}$',  # 95, 100, 105 등
        r'^FREE$',
        r'^F$',
        r'프리',
        r'미니|스몰|미디엄|라지',
        r'small|medium|large'
    ]

    detected_colors = []
    detected_sizes = []

    for part in parts:
        part_lower = part.lower().strip()
        if not part_lower:
            continue

        # 색상 체크
        is_color = False
        for color_pattern in color_patterns:
            if re.search(color_pattern, part_lower, re.IGNORECASE):
                detected_colors.append(part)
                is_color = True
                break

        # 사이즈 체크 (색상이 아닌 경우에만)
        if not is_color:
            for size_pattern in size_patterns:
                if re.match(size_pattern, part.upper()):
                    detected_sizes.append(part.upper())
                    break

    return (detected_colors if detected_colors else [], detected_sizes if detected_sizes else [])
