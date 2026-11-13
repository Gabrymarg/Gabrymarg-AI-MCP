"""Avvio della web app:  python -m webapp  (poi aprire http://127.0.0.1:8000)."""

import argparse
import sys

import uvicorn

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Web app di Osteria del Borgo")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    print(f"Osteria del Borgo: apri http://{args.host}:{args.port} nel browser (Ctrl+C per fermare)")
    uvicorn.run("webapp.app:app", host=args.host, port=args.port, log_level="warning")
