#!/usr/bin/env sh
# Build the .NET native accelerator (FolioCore + FolioCli) as a
# self-contained single-file executable. Result: ~70 MB exe that needs no
# .NET runtime installed; backend/native_accel.py picks it up automatically
# (or via FOLIO_NATIVE=<path-to-exe>).
set -e
cd "$(dirname "$0")/../dotnet"

case "$(uname -s)" in
    Linux*) rid=linux-x64 ;;
    Darwin*) rid=osx-x64 ;;
    *)      rid=win-x64 ;;
esac

dotnet publish FolioCli/FolioCli.csproj -c Release -r "$rid" \
    --self-contained true -p:PublishSingleFile=true

echo
echo "published: dotnet/FolioCli/bin/Release/net10.0/$rid/publish/"
