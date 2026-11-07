#!/bin/sh
# Installs the Pcapy Wireshark plugins: picks the installer for this OS. Options are passed through.
#   macOS   -> install-macos.sh      Linux -> install-linux.sh      Windows -> install.bat / install.ps1
HERE="$(cd "$(dirname "$0")" && pwd)"
case "$(uname -s)" in
  Darwin) exec sh "$HERE/install-macos.sh" "$@" ;;
  Linux)  exec sh "$HERE/install-linux.sh" "$@" ;;
  MINGW*|MSYS*|CYGWIN*) echo "On Windows run install.bat (or install.ps1 in PowerShell)." >&2; exit 1 ;;
  *) echo "Unsupported OS: $(uname -s)" >&2; exit 1 ;;
esac
