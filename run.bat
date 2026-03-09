@echo off
chcp 65001 >nul
echo =========================================
echo   📈 FinAgent-AI 통합 실행 스크립트 📈
echo =========================================

REM 가상환경 활성화 (venv 폴더 기준)
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
    echo [System] 가상환경(venv)이 활성화되었습니다.
) else (
    echo [경고] venv 가상환경 폴더를 찾을 수 없습니다. 전역 환경에서 실행을 시도합니다.
)

echo.
echo [1/2] 백엔드(FastAPI) 서버를 구동합니다...
start "FinAgent Backend (FastAPI)" cmd /k "uvicorn main:app --reload --port 8000"

echo [2/2] 프론트엔드(Streamlit) 화면을 띄웁니다...
start "FinAgent Frontend (Streamlit)" cmd /k "streamlit run app.py"

echo.
echo ✅ 모든 서버 실행 명령이 전달되었습니다!
echo 새로 뜬 두 개의 검은 창(터미널)을 그대로 켜두시면 됩니다.
echo (서버를 종료하고 싶을 때는 해당 창들을 X 버튼으로 닫아주세요)
pause
