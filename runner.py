# runner.py — 즉시 1회 실행 + 10분 정각마다 반복 (외부 패키지 불필요)
import subprocess
import time
from datetime import datetime, timedelta

# 실행할 스크립트들 (파일명이 다르면 여기서 바꿔주세요)
TASKS = [
    ("agoda_price_crawler.py", 0),   # 정각
    ("kayak_price_crawler.py", 20), # +20초
    ("amazon_price_crawler.py", 40),  # +40초
]

PYTHON = "python"  # 필요시 "python3" 또는 절대경로로 변경

def run(cmd):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] ▶ RUN {cmd}")
    # --once 로 단발 실행 (내부 스케줄과 충돌 방지)
    p = subprocess.run([PYTHON, cmd, "--once"], capture_output=True, text=True)
    if p.returncode != 0:
        print(f"[ERROR] {cmd} exited with {p.returncode}")
        if p.stderr:
            print(p.stderr)
    if p.stdout:
        print(p.stdout)

def seconds_until_next_10m_mark():
    now = datetime.now()
    base = now.replace(second=0, microsecond=0)
    next_min = ((now.minute // 10) + 1) * 10
    if next_min >= 60:
        run_time = (base + timedelta(hours=1)).replace(minute=0)
    else:
        run_time = base.replace(minute=next_min)
    return max(1, int((run_time - now).total_seconds()))

def main():
    print("✅ Runner started (immediate run + every 10m on :00/:10/:20...). Ctrl+C to stop.")
    # 1) 시작 즉시 한 번 실행 (스태거 적용)
    start = time.time()
    for script, delay in TASKS:
        wait = delay - (time.time() - start)
        if wait > 0:
            time.sleep(wait)
        run(script)

    # 2) 이후부터는 10분 정각마다 반복
    while True:
        wait_s = seconds_until_next_10m_mark()
        print(f"[Runner] 다음 라운드까지 {wait_s}초 대기...")
        time.sleep(wait_s)
        round_start = time.time()
        for script, delay in TASKS:
            wait = delay - (time.time() - round_start)
            if wait > 0:
                time.sleep(wait)
            run(script)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[종료] 사용자에 의해 중단되었습니다.")
