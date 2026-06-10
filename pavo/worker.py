from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class WorkerConfig:
    host: str
    port: int
    private_key: str
    environment: str
    data_dir: Path


def load_worker_config() -> WorkerConfig:
    private_key = os.environ.get("PAVO_WORKER_KEY", "").strip()
    if not private_key:
        raise RuntimeError("PAVO_WORKER_KEY is required")
    return WorkerConfig(
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8080")),
        private_key=private_key,
        environment=os.environ.get("PAVO_ENV", "development"),
        data_dir=Path(os.environ.get("PAVO_WORKER_DATA_DIR", "/data")).expanduser(),
    )


def create_worker_handler(config: WorkerConfig) -> type[BaseHTTPRequestHandler]:
    started_at = time.time()

    class PavoWorkerHandler(BaseHTTPRequestHandler):
        server_version = "PavoWorker/0.1"

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path in {"/", "/healthz"}:
                self._send_json(
                    {
                        "ok": True,
                        "service": "eidos-pavo-worker",
                        "environment": config.environment,
                        "data_dir": str(config.data_dir),
                        "data_dir_ready": config.data_dir.exists(),
                        "uptime_seconds": round(time.time() - started_at, 3),
                    }
                )
                return
            if path == "/v1/status":
                if not self._authorized():
                    self._send_auth_error()
                    return
                self._send_json(
                    {
                        "ok": True,
                        "service": "eidos-pavo-worker",
                        "mode": "private-single-user",
                        "capabilities": ["status", "manual_tick"],
                        "next_capabilities": ["plaud_sync", "fireflies_sync", "omni_routing"],
                        "data_dir": str(config.data_dir),
                        "data_dir_ready": config.data_dir.exists(),
                        "uptime_seconds": round(time.time() - started_at, 3),
                    }
                )
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path == "/v1/tick":
                if not self._authorized():
                    self._send_auth_error()
                    return
                self._send_json(
                    {
                        "ok": True,
                        "accepted": True,
                        "action": "manual_tick",
                        "message": "Pavo worker is reachable; vendor sync is not enabled yet.",
                        "planned_sources": ["plaud", "fireflies"],
                    }
                )
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def log_message(self, format: str, *args: Any) -> None:
            print(f"{self.address_string()} {self.command} {self.path} {format % args}")

        def _authorized(self) -> bool:
            provided = self.headers.get("x-pavo-worker-key", "").strip()
            authorization = self.headers.get("authorization", "").strip()
            if authorization.lower().startswith("bearer "):
                provided = authorization.split(" ", 1)[1].strip()
            return bool(provided) and provided == config.private_key

        def _send_auth_error(self) -> None:
            self._send_json({"ok": False, "error": "unauthorized"}, status=HTTPStatus.UNAUTHORIZED)

        def _send_json(self, payload: dict[str, Any], *, status: int = HTTPStatus.OK) -> None:
            body = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return PavoWorkerHandler


def main() -> None:
    config = load_worker_config()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((config.host, config.port), create_worker_handler(config))
    print(f"pavo worker listening on {config.host}:{config.port} ({config.environment})")
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
