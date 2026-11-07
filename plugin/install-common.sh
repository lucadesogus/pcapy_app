# Shared logic for install-linux.sh and install-macos.sh (sourced, not run directly).
#
# The caller defines detect_tshark() -> prints the tshark command to use, or nothing, then calls
# pcapy_main "$@". Destinations come from, in order: command-line options, Wireshark itself
# (`tshark -G folders`), then the standard personal folders.

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_NAME="$(basename "$0")"

pcapy_usage() {
  cat <<USAGE
Usage: $SCRIPT_NAME [options]

Installs the Pcapy Wireshark plugins: the "Pcapy: phone" capture interface, the Lua dissector
(pcapy.app / pcapy.uid fields) and a "Pcapy" profile with an App column.

Options:
  --uninstall          remove the plugin files (the Pcapy profile is kept)
  --extcap-dir DIR     install the capture interface here
  --plugins-dir DIR    install the Lua dissector here
  --profile-dir DIR    create the Pcapy profile here
  --tshark CMD         tshark to ask for Wireshark's folders
  -h, --help           show this help
USAGE
}

# Prints the value of one line of `tshark -G folders`, e.g. "Personal Extcap path".
pcapy_folder() {
  [ -n "$TSHARK_CMD" ] || return 0
  sh -c "$TSHARK_CMD -G folders" 2>/dev/null | sed -n "s/^$1:[[:space:]]*//p" | head -n 1
}

pcapy_resolve_dirs() {
  [ -n "$EXTCAP_DIR" ]  || EXTCAP_DIR="$(pcapy_folder 'Personal Extcap path')"
  [ -n "$PLUGINS_DIR" ] || PLUGINS_DIR="$(pcapy_folder 'Personal Lua Plugins')"
  if [ -z "$PROFILE_DIR" ]; then
    cfg="$(pcapy_folder 'Personal configuration')"
    [ -n "$cfg" ] || cfg="${XDG_CONFIG_HOME:-$HOME/.config}/wireshark"
    PROFILE_DIR="$cfg/profiles/Pcapy"
  fi
  [ -n "$EXTCAP_DIR" ]  || EXTCAP_DIR="$HOME/.local/lib/wireshark/extcap"
  [ -n "$PLUGINS_DIR" ] || PLUGINS_DIR="$HOME/.local/lib/wireshark/plugins"
}

pcapy_install() {
  mkdir -p "$EXTCAP_DIR" "$PLUGINS_DIR"
  # Old names: left in place they would show a second, stale interface and load a duplicate dissector.
  rm -f "$EXTCAP_DIR/pcapvpn_extcap.py" "$PLUGINS_DIR/pcapvpn.lua"
  cp "$HERE/extcap/pcapy_extcap.py" "$EXTCAP_DIR/pcapy_extcap.py"
  chmod +x "$EXTCAP_DIR/pcapy_extcap.py"
  cp "$HERE/lua/pcapy.lua" "$PLUGINS_DIR/pcapy.lua"
  echo "Installed extcap : $EXTCAP_DIR/pcapy_extcap.py"
  echo "Installed Lua    : $PLUGINS_DIR/pcapy.lua"
  if [ -e "$PROFILE_DIR/preferences" ]; then
    echo "Profile 'Pcapy' already exists, left untouched ($PROFILE_DIR)"
  else
    mkdir -p "$PROFILE_DIR"
    cp "$HERE/profile/preferences" "$PROFILE_DIR/preferences"
    echo "Created profile  : Pcapy ($PROFILE_DIR) - choose it in the status bar, bottom right"
  fi
  command -v python3 >/dev/null 2>&1 || \
    echo "WARNING: python3 not found. The capture interface needs Python 3 to run." >&2
  echo "Restart Wireshark to load the plugins."
}

pcapy_uninstall() {
  rm -f "$EXTCAP_DIR/pcapy_extcap.py" "$PLUGINS_DIR/pcapy.lua" \
        "$EXTCAP_DIR/pcapvpn_extcap.py" "$PLUGINS_DIR/pcapvpn.lua"
  echo "Removed the Pcapy plugin files from:"
  echo "  $EXTCAP_DIR"
  echo "  $PLUGINS_DIR"
  [ -e "$PROFILE_DIR" ] && echo "The profile was kept; delete it in Wireshark (Edit > Configuration Profiles) or remove $PROFILE_DIR"
  echo "Restart Wireshark."
}

pcapy_main() {
  MODE=install
  while [ $# -gt 0 ]; do
    case "$1" in
      --uninstall)   MODE=uninstall ;;
      --extcap-dir)  EXTCAP_DIR="$2"; shift ;;
      --plugins-dir) PLUGINS_DIR="$2"; shift ;;
      --profile-dir) PROFILE_DIR="$2"; shift ;;
      --tshark)      TSHARK_CMD="$2"; shift ;;
      -h|--help)     pcapy_usage; exit 0 ;;
      *) echo "Unknown option: $1" >&2; pcapy_usage >&2; exit 2 ;;
    esac
    shift
  done
  [ -n "$TSHARK_CMD" ] || TSHARK_CMD="$(detect_tshark)"
  pcapy_resolve_dirs
  if [ "$MODE" = uninstall ]; then pcapy_uninstall; else pcapy_install; fi
}
