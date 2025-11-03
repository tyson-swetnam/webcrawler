#!/usr/bin/env python3
"""
Simple HTTP server to preview the HTML reports locally.

Usage:
    python scripts/serve_html.py [port] [directory]

Examples:
    python scripts/serve_html.py              # Serve on port 8000 from html_output/
    python scripts/serve_html.py 8080         # Serve on port 8080
    python scripts/serve_html.py 8080 output  # Serve on port 8080 from output/
"""

import sys
import http.server
import socketserver
from pathlib import Path


def serve_html(port: int = 8000, directory: str = "html_output"):
    """Start a simple HTTP server to view HTML reports"""

    # Change to the html output directory
    html_dir = Path(directory).resolve()

    if not html_dir.exists():
        print(f"Error: Directory '{html_dir}' does not exist")
        print(f"\nRun the crawler first to generate HTML reports:")
        print(f"  python -m crawler")
        sys.exit(1)

    # Change working directory
    import os
    os.chdir(html_dir)

    # Create server
    Handler = http.server.SimpleHTTPRequestHandler

    # Disable caching for development
    Handler.extensions_map.update({
        '.html': 'text/html; charset=utf-8',
        '.css': 'text/css; charset=utf-8',
        '.js': 'application/javascript; charset=utf-8',
    })

    with socketserver.TCPServer(("", port), Handler) as httpd:
        print(f"")
        print(f"=" * 60)
        print(f"🌐 AI University News - HTML Report Server")
        print(f"=" * 60)
        print(f"")
        print(f"📁 Serving directory: {html_dir}")
        print(f"🔗 Server URL:        http://localhost:{port}")
        print(f"")
        print(f"Quick links:")
        print(f"  Today's report: http://localhost:{port}/")
        print(f"  Archive:        http://localhost:{port}/archive/")
        print(f"")
        print(f"Press Ctrl+C to stop the server")
        print(f"=" * 60)
        print(f"")

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print(f"\n\n✋ Server stopped by user")
            sys.exit(0)


if __name__ == "__main__":
    # Parse command line arguments
    port = 8000
    directory = "html_output"

    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Error: Invalid port number '{sys.argv[1]}'")
            sys.exit(1)

    if len(sys.argv) > 2:
        directory = sys.argv[2]

    serve_html(port, directory)
