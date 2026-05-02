@echo off
REM teardown.bat - unregister realestate-mcp servers from Claude Code and uninstall the uv tool.
REM Idempotent: safe to run even if setup.bat was never run.
setlocal

echo == realestate-mcp teardown ==

REM ---- locate uv (PATH first, then common pip --user location) ----
set "UV_CMD=uv"
where uv >nul 2>&1
if errorlevel 1 (
    if exist "%APPDATA%\Python\Scripts\uv.exe" (
        set "UV_CMD=%APPDATA%\Python\Scripts\uv.exe"
    ) else (
        set "UV_CMD="
    )
)

echo.
echo [1/2] Unregistering MCP servers from Claude Code (user scope)...
for %%S in (airbnb loopnet vrbo zillow) do (
    call claude mcp remove %%S --scope user >nul 2>&1 && (echo   - %%S removed) || (echo   . %%S not registered)
)

echo.
echo [2/2] Uninstalling realestate-mcp uv tool...
if defined UV_CMD (
    call "%UV_CMD%" tool uninstall realestate-mcp >nul 2>&1 && (echo   - uv tool uninstalled) || (echo   . uv tool was not installed)
) else (
    echo   . uv not found; skipping tool uninstall
)

echo.
echo Done. The local source tree and .venv are untouched.
endlocal
