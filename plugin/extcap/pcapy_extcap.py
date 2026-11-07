#!/usr/bin/env python3
"""Wireshark extcap plugin for Pcapy (live capture from a phone).

Wireshark calls this program to list the interface, build the settings dialog
(phone IP, port, password) and run the capture. Standard library only, and
compatible with Python 3.9 (the system Python on macOS).

Protocol with the phone (see core/crates/ffi/src/stream.rs):
  phone -> us:  "PCAPVPN2 <nonce>\\n"
  us -> phone:  "<hex HMAC-SHA256(key=password, msg=nonce text)>\\n"
  phone -> us:  pcapng stream (closed immediately if the password is wrong)
  A phone that is locking this computer out answers "PCAPVPN2-BLOCKED <seconds>" instead of a challenge.
"""
import argparse
import hashlib
import hmac
import socket
import sys

INTERFACE = "pcapy"
DEFAULT_PORT = 19000
DLT_RAW = 101
VERSION = "1.0.0"


class CaptureError(Exception):
    """A problem the user should read in Wireshark's error dialog."""


def read_line(sock, limit=256):
    buf = bytearray()
    while len(buf) < limit:
        b = sock.recv(1)
        if not b:
            return None
        if b == b"\n":
            return buf.decode("ascii", "replace")
        buf += b
    return None


def auth_response(password, nonce):
    return hmac.new(password.encode("utf-8"), nonce.encode("ascii"), hashlib.sha256).hexdigest()


def connect_and_auth(host, port, password, timeout=10.0):
    """Returns an authenticated socket positioned at the start of the pcapng stream."""
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
    except OSError as e:
        raise CaptureError(
            "Cannot connect to %s:%d (%s). Is the capture running on the phone, "
            "and are the phone and this computer on the same network?" % (host, port, e)
        )
    try:
        greeting = read_line(sock)
        if greeting is not None and greeting.startswith("PCAPVPN2-BLOCKED"):
            parts = greeting.split()
            secs = parts[1] if len(parts) > 1 and parts[1].isdigit() else "a few"
            raise CaptureError(
                "The phone is refusing connections from this computer for about %s more seconds "
                "(too many wrong passwords, or too many attempts at once). Wait, then try again." % secs
            )
        if greeting is None or not greeting.startswith("PCAPVPN2 "):
            raise CaptureError("%s:%d is not a Pcapy phone (unexpected greeting)." % (host, port))
        nonce = greeting[len("PCAPVPN2 "):]
        sock.sendall((auth_response(password, nonce) + "\n").encode("ascii"))
        first = sock.recv(65536)  # blocks until header arrives, or the phone closes on a bad password
        if not first:
            raise CaptureError("Authentication failed: wrong password.")
        sock.settimeout(None)
        return sock, first
    except socket.timeout:
        sock.close()
        raise CaptureError("Timed out waiting for the phone to answer.")
    except Exception:
        sock.close()
        raise


def stream(sock, first, out):
    """Copies the pcapng stream (starting with `first`) into `out` until the phone closes."""
    try:
        out.write(first)
        out.flush()
        while True:
            data = sock.recv(65536)
            if not data:
                break
            out.write(data)
            out.flush()
    finally:
        sock.close()


def capture(host, port, password, out):
    sock, first = connect_and_auth(host, port, password)
    stream(sock, first, out)


def print_interfaces():
    print("extcap {version=%s}" % VERSION)
    print("interface {value=%s}{display=Pcapy: phone}" % INTERFACE)


def print_dlts():
    print("dlt {number=%d}{name=RAW}{display=Raw IP}" % DLT_RAW)


def print_config():
    print("arg {number=0}{call=--host}{display=Phone IP address}{type=string}{required=true}"
          "{tooltip=IP address shown in the Pcapy app on the phone}")
    print("arg {number=1}{call=--port}{display=Port}{type=integer}{range=1,65535}"
          "{default=%d}{tooltip=Stream port shown in the Pcapy app}" % DEFAULT_PORT)
    print("arg {number=2}{call=--password}{display=Password}{type=password}{required=true}"
          "{tooltip=The password you set in the Pcapy app}")


def build_parser():
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--extcap-interfaces", action="store_true")
    p.add_argument("--extcap-version")
    p.add_argument("--extcap-interface")
    p.add_argument("--extcap-dlts", action="store_true")
    p.add_argument("--extcap-config", action="store_true")
    p.add_argument("--capture", action="store_true")
    p.add_argument("--fifo")
    p.add_argument("--host")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--password")
    return p


def main(argv=None):
    args, _unknown = build_parser().parse_known_args(argv)  # Wireshark passes extra options
    if args.extcap_interfaces:
        print_interfaces()
        return 0
    if args.extcap_dlts:
        print_dlts()
        return 0
    if args.extcap_config:
        print_config()
        return 0
    if args.capture:
        if not args.fifo:
            sys.stderr.write("Missing --fifo\n")
            return 2
        if not args.host or not args.password:
            sys.stderr.write("Enter the phone's IP address and password in the interface options.\n")
            return 2
        try:
            # Authenticate BEFORE opening the fifo, so errors reach the user's dialog.
            sock, first = connect_and_auth(args.host, args.port, args.password)
            with open(args.fifo, "wb") as out:
                stream(sock, first, out)
        except CaptureError as e:
            sys.stderr.write("%s\n" % e)
            return 1
        except (BrokenPipeError, KeyboardInterrupt):
            pass
        return 0
    sys.stderr.write("Nothing to do. This program is meant to be run by Wireshark.\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
