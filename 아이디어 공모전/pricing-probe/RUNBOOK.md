# RUNBOOK
## 설치
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
# (OCR 사용 시) Tesseract 설치 필요

## 실행
python -m src.orchestrator --platform agoda --once
python -m src.orchestrator --platform amazon --once
python -m src.orchestrator --platform kayak --once
