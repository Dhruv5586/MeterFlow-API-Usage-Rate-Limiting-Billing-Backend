#!/usr/bin/env python3
"""
MeterFlow — Server Startup Script
---------------------------------
Starts the Uvicorn ASGI server with proper path resolution and configuration.
Supports optional --port and --host command-line flags.
"""

import os
import sys
import socket
import argparse
from pathlib import Path

# Ensure project root is in sys.path
root_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import uvicorn
from app.core.config import settings


def is_port_available(host: str, port: int) -> bool:
    """Checks whether a local port is available for binding."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return True
        except OSError:
            return False


def find_available_port(host: str, starting_port: int, max_attempts: int = 10) -> int:
    """Finds the first available port starting from starting_port."""
    for p in range(starting_port, starting_port + max_attempts):
        if is_port_available(host, p):
            return p
    return starting_port


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start MeterFlow Development Server")
    parser.add_argument("--port", type=int, default=settings.PORT, help="Port to bind (default: 8000)")
    parser.add_argument("--host", type=str, default=settings.HOST, help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--no-reload", action="store_true", help="Disable auto-reload")
    args, _ = parser.parse_known_args()

    target_host = args.host
    target_port = args.port

    if not is_port_available(target_host, target_port):
        alt_port = find_available_port(target_host, target_port + 1)
        print("=" * 70)
        print(f"[!] Warning: Port {target_port} is already in use by another process.")
        print(f"[+] Automatically switching to free port: http://{target_host}:{alt_port}")
        print("=" * 70)
        target_port = alt_port

    print("=" * 70)
    print(f" Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    print(f" Host:        http://{target_host}:{target_port}")
    print(f" Swagger UI:  http://{target_host}:{target_port}/docs")
    print(f" ReDoc UI:    http://{target_host}:{target_port}/redoc")
    print(f" Health:      http://{target_host}:{target_port}/api/v1/health")
    print("=" * 70)

    uvicorn.run(
        "app.main:app",
        host=target_host,
        port=target_port,
        reload=not args.no_reload,
        log_level=settings.LOG_LEVEL.lower(),
    )
