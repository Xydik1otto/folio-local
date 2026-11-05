@echo off
REM Build the .NET native accelerator (FolioCore + FolioCli) as a
REM self-contained single-file executable for Windows.
REM backend/native_accel.py picks up the exe automatically (or via FOLIO_NATIVE).
cd /d "%~dp0..\dotnet"
dotnet publish FolioCli\FolioCli.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true
echo.
echo published: dotnet\FolioCli\bin\Release\net10.0\win-x64\publish\FolioCli.exe
