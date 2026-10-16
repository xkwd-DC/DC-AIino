@echo off
rem ---------------------------------------------------------------------------
rem  DC grain-risk system - local launcher (the desktop shortcut points here)
rem
rem  Keep this file ASCII-ONLY on purpose. cmd.exe parses .bat/.cmd line by line
rem  using the ACTIVE code page; a UTF-8 file with Chinese comments gets decoded
rem  as GBK and the mojibake can split a `rem` line into garbage commands.
rem  All Chinese messages live in serve_local.ps1 (UTF-8 with BOM) instead.
rem ---------------------------------------------------------------------------
chcp 65001 >nul
title DC grain-risk system - local

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0serve_local.ps1" -Open

echo.
echo Service keeps running in the background - closing this window will NOT stop it.
echo To stop it:  powershell -ExecutionPolicy Bypass -File "%~dp0serve_local.ps1" -Stop
echo.
pause
