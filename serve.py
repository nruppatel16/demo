#!/usr/bin/env python3
"""Start a local HTTP server accessible from any device on your network."""
import http.server
import socket
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5000

def get_local_ip():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"

handler = http.server.SimpleHTTPRequestHandler

with http.server.HTTPServer(("0.0.0.0", PORT), handler) as httpd:
    ip = get_local_ip()
    print(f"\n  Weather app running!")
    print(f"\n  On this device : http://localhost:{PORT}")
    print(f"  On your phone  : http://{ip}:{PORT}")
    print(f"\n  (Make sure your phone is on the same Wi-Fi network)")
    print(f"  Press Ctrl+C to stop.\n")
    httpd.serve_forever()
