import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from pavo.worker import WorkerConfig, create_worker_handler


class WorkerTests(unittest.TestCase):
    def test_private_status_requires_worker_key(self):
        with self._server() as base_url:
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(f"{base_url}/v1/status", timeout=2)

            self.assertEqual(raised.exception.code, 401)

    def test_private_status_accepts_worker_key(self):
        with self._server() as base_url:
            request = urllib.request.Request(
                f"{base_url}/v1/status",
                headers={"X-Pavo-Worker-Key": "secret"},
            )

            with urllib.request.urlopen(request, timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["mode"], "private-single-user")
        self.assertIn("manual_tick", payload["capabilities"])

    def test_healthz_is_public(self):
        with self._server() as base_url:
            with urllib.request.urlopen(f"{base_url}/healthz", timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["service"], "eidos-pavo-worker")

    def test_manual_tick_accepts_worker_key(self):
        with self._server() as base_url:
            request = urllib.request.Request(
                f"{base_url}/v1/tick",
                data=b"{}",
                method="POST",
                headers={"Authorization": "Bearer secret"},
            )

            with urllib.request.urlopen(request, timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))

        self.assertTrue(payload["accepted"])
        self.assertEqual(payload["action"], "manual_tick")

    class _server:
        def __enter__(self):
            config = WorkerConfig(host="127.0.0.1", port=0, private_key="secret", environment="test")
            self.server = ThreadingHTTPServer(("127.0.0.1", 0), create_worker_handler(config))
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            host, port = self.server.server_address
            return f"http://{host}:{port}"

        def __exit__(self, exc_type, exc, tb):
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=2)
