@echo off
REM =====================================================================
REM Tank-Orakel - nightly curve update (Windows Task Scheduler job).
REM
REM Downloads only the needed day-files from the Tankerkoenig historical
REM data over HTTPS (no 20 GB clone), rebuilds curve.json, and pushes it
REM so Cloudflare Pages redeploys with the fresh curve.
REM
REM Prerequisite: a free Azure DevOps account + a Personal Access Token
REM with scope "Code (Read)". Store it as a USER environment variable
REM named TK_AZURE_PAT (setx TK_AZURE_PAT "<token>") so it is not in the
REM repo. Register the task once (adjust the path):
REM   schtasks /Create /SC DAILY /ST 05:00 /TN "Tank-Orakel-Curve" ^
REM     /TR "C:\path\to\Tank-orakel\tools\update_curve.bat"
REM =====================================================================
setlocal
set REPO_DIR=%~dp0..
set WINDOW=90

cd /d "%REPO_DIR%" || exit /b 1

if "%TK_AZURE_PAT%"=="" (
  echo ERROR: TK_AZURE_PAT is not set. Create an Azure DevOps PAT ^(Code: Read^)
  echo        and run:  setx TK_AZURE_PAT "your-token"   then reopen the shell.
  exit /b 1
)

echo [1/3] Building curve.json (downloading needed day-files) ...
python "%REPO_DIR%\tools\build_curve.py" --out "%REPO_DIR%\curve.json" --window %WINDOW% --cache "%REPO_DIR%\data\cache" || exit /b 1

echo [2/3] Committing ...
git add curve.json
git diff --cached --quiet && (echo   no change & goto :done)
git commit -m "Update curve.json (automated)" || exit /b 1

echo [3/3] Pushing ...
git push origin main || exit /b 1

:done
echo Done.
endlocal
