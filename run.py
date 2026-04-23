"""
FinAgent-AI 통합 실행 스크립트.

기본 실행 (처음 세팅 ~ 서비스 기동까지 한 번에):
    python run.py

단계:
  1) pip install -r requirements.txt
  2) python -m rag.economic_news  (오늘 파일이 없을 때만 자동 수집; 이미 있으면 건너뜀 → 재수집은 Streamlit 또는 --news-force)
  3) python -m rag.vector_store   (data/ 기반 FAISS 인덱스 생성)
  4) FastAPI(8000) + Streamlit(8501) 동시 기동

서버만 빠르게 켤 때 (이미 패키지·뉴스·인덱스가 준비된 경우):
    python run.py --serve-only

일부 단계만 건너뛰기:
    python run.py --no-pip
    python run.py --no-news
    python run.py --no-faiss

뉴스 강제 수집(터미널):
    python run.py --news-force          # 오늘 파일이 있어도 RSS·요약 전체 다시 실행

가상환경 사용 시 프로젝트 루트에서 venv 활성화 후 실행하는 것을 권장합니다.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQUIREMENTS = ROOT / "requirements.txt"
_KST = timezone(timedelta(hours=9))


def _news_data_dir() -> Path:
    raw = os.getenv("DATA_PATH", "data")
    p = Path(raw)
    return p.resolve() if p.is_absolute() else (ROOT / p).resolve()


def _todays_news_file_path() -> Path:
    """economic_news.py 와 동일: KST 기준 news_YYYYMMDD.txt"""
    tag = datetime.now(_KST).strftime("%Y%m%d")
    return _news_data_dir() / f"news_{tag}.txt"


def _run_step(
    title: str,
    argv: list[str],
    *,
    cwd: Path | None = None,
    optional: bool = False,
) -> bool:
    """서브프로세스 실행. optional=True면 실패해도 False만 반환하고 예외 없이 진행."""
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)
    cmd = " ".join(argv)
    print(f"$ {cmd}\n")
    try:
        r = subprocess.run(
            argv,
            cwd=cwd or ROOT,
            check=False,
        )
    except OSError as e:
        print(f"[오류] 실행 실패: {e}")
        return False
    if r.returncode != 0:
        msg = f"명령이 종료 코드 {r.returncode} 로 끝났습니다."
        if optional:
            print(f"[경고] {msg} (선택 단계이므로 계속합니다.)")
            return False
        print(f"[오류] {msg}")
        return False
    print("[완료]")
    return True


def step_pip_install() -> bool:
    if not REQUIREMENTS.is_file():
        print(f"[오류] {REQUIREMENTS} 파일이 없습니다.")
        return False
    return _run_step(
        "[1/4] 필수 패키지 설치 (pip install -r requirements.txt)",
        [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)],
    )


def _should_run_news_collection(*, force: bool) -> bool:
    """
    True 이면 rag.economic_news 를 실행한다.
    오늘 파일이 이미 있으면 기본은 건너뜀(재수집은 Streamlit UI 또는 --news-force).
    """
    path = _todays_news_file_path()
    if not path.is_file() or path.stat().st_size == 0:
        return True

    if force:
        print(f"\n[뉴스] --news-force: 기존 파일을 덮어쓰며 다시 수집합니다.\n  {path}")
        return True

    print(
        f"\n[건너뜀] 오늘 뉴스 파일이 이미 있습니다. (빠른 기동)\n  {path.resolve()}\n"
        "  다시 수집: 웹 화면 「오늘 뉴스 수집」에서 실행, 또는 터미널에서 python run.py --news-force"
    )
    return False


def step_economic_news(*, force: bool = False) -> bool:
    if not _should_run_news_collection(force=force):
        return True
    return _run_step(
        "[2/4] 오늘의 경제·증시 뉴스 수집 (python -m rag.economic_news)",
        [sys.executable, "-m", "rag.economic_news"],
        optional=True,
    )


def step_faiss() -> bool:
    return _run_step(
        "[3/4] Vector DB(FAISS) 초기화 (python -m rag.vector_store)",
        [sys.executable, "-m", "rag.vector_store"],
        optional=True,
    )


def ensure_streamlit() -> bool:
    if importlib.util.find_spec("streamlit") is None:
        print(
            "\n[경고] 현재 파이썬 환경에 'streamlit'이 없습니다.\n"
            "가상환경을 활성화했는지 확인하거나, 아래를 먼저 실행하세요.\n"
            f"  {sys.executable} -m pip install -r requirements.txt\n"
        )
        return False
    return True


def run_servers() -> None:
    print("\n" + "=" * 60)
    print("[4/4] 백엔드(FastAPI) + 프론트엔드(Streamlit) 기동")
    print("=" * 60)

    if not ensure_streamlit():
        sys.exit(1)

    python_exe = sys.executable
    print("[4a] 백엔드(FastAPI) 시작 중... (port 8000)")
    backend_process = subprocess.Popen(
        [python_exe, "-m", "uvicorn", "main:app", "--reload", "--port", "8000"],
        cwd=ROOT,
    )

    time.sleep(3)

    print("[4b] 프론트엔드(Streamlit) 시작 중... (port 8501)")
    # Streamlit 기본 동작도 브라우저를 열므로, headless로 두고 아래에서 한 번만 연다.
    frontend_process = subprocess.Popen(
        [
            python_exe,
            "-m",
            "streamlit",
            "run",
            "app.py",
            "--server.headless=true",
        ],
        cwd=ROOT,
    )

    time.sleep(2)
    print("\n서버 구동 완료. 브라우저를 엽니다... (Streamlit: http://localhost:8501 )")
    webbrowser.open("http://localhost:8501")

    print("\n종료: 이 터미널에서 Ctrl+C")
    print("-" * 60)

    try:
        backend_process.wait()
        frontend_process.wait()
    except KeyboardInterrupt:
        print("\n\n종료 명령(Ctrl+C) — 서버를 종료합니다...")
        backend_process.terminate()
        frontend_process.terminate()
        print("종료되었습니다.")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="패키지 설치 → 뉴스 수집 → FAISS 초기화 → 서버 기동까지 한 번에 실행합니다.",
    )
    p.add_argument(
        "--serve-only",
        action="store_true",
        help="서버만 실행합니다 (pip / 뉴스 / FAISS 단계 생략).",
    )
    p.add_argument("--no-pip", action="store_true", help="pip 설치 단계를 건너뜁니다.")
    p.add_argument("--no-news", action="store_true", help="뉴스 수집 단계를 건너뜁니다.")
    p.add_argument("--no-faiss", action="store_true", help="FAISS 초기화 단계를 건너뜁니다.")
    p.add_argument(
        "--news-force",
        action="store_true",
        help="오늘 news_YYYYMMDD.txt 가 있어도 뉴스 수집을 다시 실행합니다.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    print("FinAgent-AI 통합 실행\n프로젝트 루트:", ROOT)

    if args.serve_only:
        run_servers()
        return

    ok = True
    if not args.no_pip:
        ok = step_pip_install()
        if not ok:
            sys.exit(1)
    else:
        print("\n[건너뜀] pip 설치 (--no-pip)")

    if not args.no_news:
        step_economic_news(force=args.news_force)
    else:
        print("\n[건너뜀] 뉴스 수집 (--no-news)")

    if not args.no_faiss:
        step_faiss()
    else:
        print("\n[건너뜀] FAISS 초기화 (--no-faiss)")

    run_servers()


if __name__ == "__main__":
    main()
