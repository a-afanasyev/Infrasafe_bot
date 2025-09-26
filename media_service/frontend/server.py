#!/usr/bin/env python3
"""
Простой HTTP сервер для тестового фронтенда MediaService
"""

import http.server
import socketserver
import os
import sys
from urllib.parse import urlparse

PORT = 3000

class CORSHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler с поддержкой CORS для работы с API"""

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

def main():
    # Меняем директорию на папку с фронтендом
    frontend_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(frontend_dir)

    print(f"🚀 Starting frontend server...")
    print(f"📁 Serving files from: {frontend_dir}")
    print(f"🌐 Frontend URL: http://localhost:{PORT}")
    print(f"🔗 MediaService API: http://localhost:8001")
    print(f"📚 API Docs: http://localhost:8001/docs")
    print(f"\n🎯 Open http://localhost:{PORT} to test MediaService frontend\n")

    try:
        with socketserver.TCPServer(("", PORT), CORSHTTPRequestHandler) as httpd:
            print(f"Server running on port {PORT}...")
            print("Press Ctrl+C to stop")
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Server stopped")
    except OSError as e:
        if e.errno == 48:  # Address already in use
            print(f"❌ Port {PORT} is already in use. Try a different port or stop the existing server.")
            sys.exit(1)
        else:
            raise

if __name__ == "__main__":
    main()