#!/bin/sh
# Installs the Pcapy Wireshark plugins on Linux. Run with --help for options.
. "$(dirname "$0")/install-common.sh"

detect_tshark() {
  if command -v tshark >/dev/null 2>&1; then
    command -v tshark
  elif command -v flatpak >/dev/null 2>&1 && flatpak info org.wireshark.Wireshark >/dev/null 2>&1; then
    echo "flatpak run --command=tshark org.wireshark.Wireshark"
  fi
}

if ! command -v tshark >/dev/null 2>&1; then
  if command -v snap >/dev/null 2>&1 && snap list wireshark >/dev/null 2>&1; then
    echo "Note: Wireshark is installed as a Snap. Snap confinement can hide plugins in ~/.local;" >&2
    echo "      if the interface does not appear, install Wireshark from your distribution instead." >&2
  fi
fi

pcapy_main "$@"
