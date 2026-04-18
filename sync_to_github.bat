@echo off
setlocal EnableExtensions

REM === Source and target folders ===
REM SRC: burada kod üzərində işlədiyin “iş masası” qovluğu
set "SRC=C:\Users\bayra\OneDrive\Desktop\Clopos_online"

REM DST: GitHub repo-nun LOCAL qovluğu (GitHub adı ilə eyni olmalı deyil)
REM İstəsən özün dəqiq yolu buraya yaza bilərsən:
REM   set "REPO_DIR=C:\Users\bayra\OneDrive\Desktop\YOUR_LOCAL_REPO_FOLDER"
if not defined REPO_DIR (
  if exist "C:\Users\bayra\OneDrive\Desktop\clopos-room\" (
    set "REPO_DIR=C:\Users\bayra\OneDrive\Desktop\clopos-room"
  ) else if exist "C:\Users\bayra\OneDrive\Desktop\clopos-bot-clean2\" (
    set "REPO_DIR=C:\Users\bayra\OneDrive\Desktop\clopos-bot-clean2"
  ) else (
    REM Son çarə: batch faylının olduğu qovluq (əgər sync repo kökündədirsə)
    set "REPO_DIR=%~dp0"
  )
)
set "DST=%REPO_DIR%"

REM Make Git available when launched from Explorer (sometimes PATH is shorter)
set "PATH=%PATH%;C:\Program Files\Git\bin;C:\Program Files\Git\cmd;C:\Program Files (x86)\Git\bin;C:\Program Files (x86)\Git\cmd"

REM === Commit message with timestamp ===
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HH-mm-ss"') do set "TS=%%i"
set "MSG=auto sync %TS%"

echo.
echo [0/6] Checking paths...
if not exist "%SRC%\" (
  echo ERROR: Source folder not found:
  echo   %SRC%
  pause
  exit /b 1
)
if not exist "%DST%\" (
  echo ERROR: Repo folder not found:
  echo   %DST%
  echo.
  echo Fix REPO_DIR at top of sync_to_github.bat OR create one of these folders:
  echo   C:\Users\bayra\OneDrive\Desktop\clopos-room
  echo   C:\Users\bayra\OneDrive\Desktop\clopos-bot-clean2
  pause
  exit /b 1
)

where git >nul 2>&1
if errorlevel 1 (
  echo ERROR: git not found in PATH.
  echo Install Git for Windows, or add git.exe folder to PATH.
  pause
  exit /b 1
)

echo [1/6] Copying files...
call :copy_one "%SRC%\app.py" "%DST%\app.py" || exit /b 1
call :copy_one "%SRC%\rules.py" "%DST%\rules.py" || exit /b 1
call :copy_one "%SRC%\requirements.txt" "%DST%\requirements.txt" || exit /b 1
call :copy_one "%SRC%\ana_biblioteka_horeca.xlsx" "%DST%\ana_biblioteka_horeca.xlsx" || exit /b 1

echo [2/6] Repo sanity check...
git -C "%DST%" rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
  echo ERROR: %DST% is not a git repository (.git missing).
  pause
  exit /b 1
)

echo Repo folder:
echo   %DST%
echo git remote:
git -C "%DST%" remote -v

echo [3/6] Staging changes...
git -C "%DST%" add app.py rules.py requirements.txt ana_biblioteka_horeca.xlsx
if errorlevel 1 (
  echo ERROR: git add failed.
  pause
  exit /b 1
)

echo [4/6] Checking if there is anything to commit...
git -C "%DST%" diff --cached --quiet
if errorlevel 1 (
  echo Changes detected. Committing...
) else (
  echo Nothing to commit (no changes after copy). Skipping commit/push.
  pause
  exit /b 0
)

echo [5/6] Committing...
git -C "%DST%" commit -m "%MSG%"
if errorlevel 1 (
  echo ERROR: git commit failed.
  pause
  exit /b 1
)

echo [6/6] Pushing to GitHub...
git -C "%DST%" push
if errorlevel 1 (
  echo Push failed. Check git remote/auth.
  pause
  exit /b 1
)

echo.
echo Done. Files synced to GitHub successfully.
pause
exit /b 0

:copy_one
set "FROM=%~1"
set "TO=%~2"
if not exist "%FROM%" (
  echo ERROR: Source file missing:
  echo   %FROM%
  pause
  exit /b 1
)
copy /Y "%FROM%" "%TO%" >nul
if errorlevel 1 (
  echo ERROR: copy failed:
  echo   %FROM%
  echo   -^> %TO%
  pause
  exit /b 1
)
echo OK: %~nx1
exit /b 0
