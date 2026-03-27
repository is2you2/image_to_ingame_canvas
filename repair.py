import sys
import os
import json
import subprocess
import math
from PIL import Image


# ==========================================
# 1. 하드코딩된 경로 설정
# ==========================================

PALETTE_JSON_PATH = "/home/liss22/두근두근타운_두타그녀_캔버스/00_palette.json"
CONFIG_JSON_PATH = "/home/liss22/두근두근타운_두타그녀_캔버스/01_canvas_config.json"
SCREENSHOT_HOST_PATH = "/home/liss22/Downloads/mobile_capture.png"      # 호스트에 저장될 스크린샷 경로
SCREENSHOT_MOBILE_PATH = "/sdcard/screen_temp.png"  # 모바일 내부 임시 경로

# 스크린샷 렌더링 시 발생하는 미세한 색상 변이를 무시하기 위한 오차 허용 범위
COLOR_TOLERANCE = 32


def run_command(cmd):
    """시스템 명령어를 실행합니다."""
    try:
        subprocess.run(cmd, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[Error] Command failed: {e}")


def get_color_distance(rgb1, rgb2):
    """두 RGB 색상 간의 유클리드 거리를 계산합니다."""
    return math.sqrt(sum([(a - b) ** 2 for a, b in zip(rgb1, rgb2)]))


def hex_to_rgb(hex_str):
    """Hex 색상을 RGB 튜플로 변환합니다."""
    hex_str = hex_str.lstrip('#')
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))


def main():
    if len(sys.argv) < 2:
        print("Usage: python repair.py <target_image_path>")
        return

    target_img_path = sys.argv[1]
    if not os.path.exists(target_img_path):
        print(f"[Error] File not found: {target_img_path}")
        return

    # 2. JSON 설정 불러오기
    with open(PALETTE_JSON_PATH, 'r', encoding='utf-8') as f:
        palette_data = json.load(f)
    with open(CONFIG_JSON_PATH, 'r', encoding='utf-8') as f:
        config_data = json.load(f)

    # 3. 모바일 스크린샷 캡처 및 풀링
    print("[Step 1] Capturing mobile screen...")
    run_command(f"adb shell screencap -p {SCREENSHOT_MOBILE_PATH}")
    run_command(f"adb pull {SCREENSHOT_MOBILE_PATH} {SCREENSHOT_HOST_PATH}")
    run_command(f"adb shell rm {SCREENSHOT_MOBILE_PATH}")

    # 4. 이미지 및 데이터 준비
    target_img = Image.open(target_img_path).convert('RGB')
    screenshot = Image.open(SCREENSHOT_HOST_PATH).convert('RGB')

    t_width, t_height = target_img.size
    ratio_str = f"{t_width}:{t_height}"  # 규격 식별용

    # 01_canvas_config에서 해당 크기에 맞는 설정 찾기
    cfg = next((item for item in config_data if item['width'] == t_width and item['height'] == t_height), None)
    if not cfg:
        print(f"[Error] No matching config found for size {t_width}x{t_height}")
        return

    # 팔레트 RGB 리스트 미리 변환 (비교 속도 향상)
    palette_rgbs = [hex_to_rgb(p['color']) for p in palette_data]

    # 5. 검토 단계: 누락된 픽셀 찾기
    todo_tasks = {i: [] for i in range(len(palette_data))}

    scaleX = cfg['sizeX'] / cfg['width']
    scaleY = cfg['sizeY'] / cfg['height']
    baseX, baseY = cfg['startX'], cfg['startY']

    print("[Step 2] Comparing target with screenshot...")

    for y in range(t_height):
        for x in range(t_width):
            # 목표 이미지의 색상을 가장 가까운 팔레트 색상으로 매칭
            target_pixel_rgb = target_img.getpixel((x, y))
            best_p_idx = 0
            min_dist = float('inf')
            for i, p_rgb in enumerate(palette_rgbs):
                dist = get_color_distance(target_pixel_rgb, p_rgb)
                if dist < min_dist:
                    min_dist = dist
                    best_p_idx = i

            intended_rgb = palette_rgbs[best_p_idx]

            # 실제 모바일 화면에서의 정가운데 좌표 계산
            tx = int(baseX + (x + 0.5) * scaleX)
            ty = int(baseY + (y + 0.5) * scaleY)

            # 스크린샷의 실제 색상 확인
            actual_rgb = screenshot.getpixel((tx, ty))

            # 오차 범위 초과하면 보수 대상에 추가
            if get_color_distance(intended_rgb, actual_rgb) > COLOR_TOLERANCE:
                todo_tasks[best_p_idx].append((tx, ty))

    # 6. 보강 단계: 팔레트 순서대로 ADB 명령 실행
    print("[Step 3] Repairing missing pixels...")
    total_repaired = 0

    for i, p_item in enumerate(palette_data):
        pixels = todo_tasks[i]

        print(f" - Color {p_item['color']}: Repairing {len(pixels)} pixels...")

        # 해당 색상 선택 명령 실행 (여러 줄 명령어도 처리)
        for sub_cmd in p_item['cmd'].split('\n'):
            if sub_cmd.strip():
                run_command(sub_cmd.strip())

        if not pixels:
            continue

        # 누락된 픽셀들 탭하기
        for (tx, ty) in pixels:
            run_command(f"adb shell input tap {tx} {ty}")
            total_repaired += 1

    print(f"\n[Done] Process finished. Total {total_repaired} pixels repaired.")


if __name__ == "__main__":
    main()