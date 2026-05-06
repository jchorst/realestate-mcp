@echo off
REM setup.bat - install realestate-mcp servers and register implemented ones with Claude Code.
REM Idempotent: safe to re-run.
setlocal

echo == realestate-mcp setup ==

REM ---- locate uv (PATH first, then common pip --user location) ----
set "UV_CMD=uv"
where uv >nul 2>&1
if errorlevel 1 (
    if exist "%APPDATA%\Python\Scripts\uv.exe" (
        set "UV_CMD=%APPDATA%\Python\Scripts\uv.exe"
    ) else (
        echo ERROR: uv not found on PATH or in %%APPDATA%%\Python\Scripts.
        echo Install from https://docs.astral.sh/uv/ or run: winget install astral-sh.uv
        exit /b 1
    )
)

where claude >nul 2>&1
if errorlevel 1 (
    echo ERROR: claude CLI is not on PATH. Install Claude Code first.
    exit /b 1
)

REM ---- 1. sync project deps ----
echo.
echo [1/3] Syncing project dependencies...
call "%UV_CMD%" sync
if errorlevel 1 exit /b 1

REM ---- 2. install as a uv tool so entry points (airbnb-mcp, ...) land on PATH globally ----
echo.
echo [2/3] Installing realestate-mcp as a uv tool (editable)...
call "%UV_CMD%" tool install --editable . --force
if errorlevel 1 exit /b 1
call "%UV_CMD%" tool update-shell >nul 2>&1

REM ---- 3. register implemented MCP servers with Claude Code (user scope) ----
echo.
echo [3/3] Registering MCP servers with Claude Code (user scope)...

REM airbnb - implemented (search_stays, get_listing_details)
call claude mcp remove airbnb --scope user >nul 2>&1
call claude mcp add --scope user airbnb -- airbnb-mcp
if errorlevel 1 exit /b 1
echo   + airbnb

REM carolinadesigns - implemented (search_rentals, get_rental_details)
call claude mcp remove carolinadesigns --scope user >nul 2>&1
call claude mcp add --scope user carolinadesigns -- carolinadesigns-mcp
if errorlevel 1 exit /b 1
echo   + carolinadesigns

REM twiddy - implemented (search_rentals, get_rental_details)
call claude mcp remove twiddy --scope user >nul 2>&1
call claude mcp add --scope user twiddy -- twiddy-mcp
if errorlevel 1 exit /b 1
echo   + twiddy

REM surforsound - implemented (search_rentals, get_rental_details)
call claude mcp remove surforsound --scope user >nul 2>&1
call claude mcp add --scope user surforsound -- surforsound-mcp
if errorlevel 1 exit /b 1
echo   + surforsound

REM sunrealty - implemented (search_rentals, get_rental_details)
call claude mcp remove sunrealty --scope user >nul 2>&1
call claude mcp add --scope user sunrealty -- sunrealty-mcp
if errorlevel 1 exit /b 1
echo   + sunrealty

REM Stub (loopnet) only exposes a 'ping' tool today; not registered to keep
REM Claude Code's tool list clean. Uncomment when implemented:
REM call claude mcp remove loopnet --scope user >nul 2>&1
REM call claude mcp add --scope user loopnet -- loopnet-mcp

echo.
echo Done. Restart any open Claude Code sessions to pick up the new servers.
echo Verify with: claude mcp list
endlocal
