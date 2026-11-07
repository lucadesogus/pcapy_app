#!/bin/sh
# Installs the Pcapy Wireshark plugins on macOS. Run with --help for options.
. "$(dirname "$0")/install-common.sh"

detect_tshark() {
  if command -v tshark >/dev/null 2>&1; then
    command -v tshark
  elif [ -x /Applications/Wireshark.app/Contents/MacOS/tshark ]; then
    echo /Applications/Wireshark.app/Contents/MacOS/tshark
  fi
}

pcapy_main "$@"
