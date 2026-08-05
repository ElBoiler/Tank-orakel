@echo off
REM =====================================================================
REM Tank-Orakel - nightly curve update (Windows Task Scheduler job).
REM
REM Pulls the latest Tankerkoenig historical data, rebuilds curve.json,
REM and pushes it so Cloudflare Pages redeploys with the fresh curve.
REM
REM Adjust DATA_DIR to where you cloned the Tankerkoenig data repo.
REM Register once (run as your user, adjust the path):
REM   schtasks /Create /SC DAILY /ST 05:00 /TN "Tank-Orakel-Curve" ^
REM     /TR "C:\path\to\Tank-orakel\tools\update_curve.bat"
REM =====================================================================
setlocal
set REPO_DIR=%~dp0..
set DATA_DIR=%REPO_DIR%\data\tankerkoenig-data
set WINDOW=90

cd /d "%REPO_DIR%" || exit /b 1

echo [1/4] Updating Tankerkoenig data ...
git -C "%DATA_DIR%" pull --ff-only || echo   (pull failed - using existing data)

echo [2/4] Building curve.json ...
python "%REPO_DIR%\tools\build_curve.py" --data "%DATA_DIR%" --out "%REPO_DIR%\curve.json" --window %WINDOW% || exit /b 1

echo [3/4] Committing ...
git add curve.json
git diff --cached --quiet && (echo   no change & goto :done)
git commit -m "Update curve.json (automated)" || exit /b 1

echo [4/4] Pushing ...
git push origin main || exit /b 1

:done
echo Done.
endlocal
