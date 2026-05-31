"""
Static API Server for Web UI Dashboard.

Provides REST endpoints consuming the unified presentation layer.
"""
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

from .. import Graph
from ..presentation import GraphPresenter


class APIHandler(BaseHTTPRequestHandler):
    presenter = None

    def do_GET(self):
        if self.path == "/api/taxonomy/summary":
            self._handle_taxonomy_summary()
        elif self.path == "/api/concerns/top":
            self._handle_top_concerns()
        elif self.path.startswith("/api/concerns?"):
            self._handle_concerns_filtered()
        elif self.path == "/api/tasks/pending":
            self._handle_pending_tasks()
        elif self.path == "/api/dependencies/cycles":
            self._handle_cycles()
        else:
            self.send_error(404, "Not Found")

    def _handle_taxonomy_summary(self):
        result = self.presenter.taxonomy.get_taxonomy_summary()
        self._send_json(result)

    def _handle_top_concerns(self):
        result = self.presenter.concerns.get_top_concerns(50)
        self._send_json(result)

    def _handle_concerns_filtered(self):
        # Parse query params
        params = {}
        query = self.path.split("?", 1)[1] if "?" in self.path else ""
        for p in query.split("&"):
            if "=" in p:
                k, v = p.split("=", 1)
                params[k] = v

        if "domain" in params:
            result = self.presenter.concerns.get_concerns_by_domain(params["domain"])
        elif "severity" in params:
            result = self.presenter.concerns.get_concerns_by_severity(params["severity"])
        else:
            result = self.presenter.concerns.get_top_concerns()

        self._send_json(result)

    def _handle_pending_tasks(self):
        result = self.presenter.tasks.get_pending_tasks()
        self._send_json(result)

    def _handle_cycles(self):
        result = self.presenter.dependencies.get_cycles()
        self._send_json(result)

    def _send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, indent=2).encode())

    def log_message(self, format, *args):
        pass  # Suppress logging


def run_server(port: int = 8080):
    """Run the API server."""
    g = Graph()
    g.build_folder_taxonomy()
    g.register_taxonomy_dependencies()
    g.register_concern_targets()

    APIHandler.presenter = GraphPresenter(g)

    server = HTTPServer(("0.0.0.0", port), APIHandler)
    print(f"API server running on http://localhost:{port}")
    server.serve_forever()