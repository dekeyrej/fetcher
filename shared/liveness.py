from http.server import HTTPServer, BaseHTTPRequestHandler
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
import os
import threading

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/live':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"alive"}')
        else:
            self.send_response(404)
            self.end_headers()

def start_liveness_probe():
    port = int(os.getenv('LIVENESS_PORT', 0))
    if port > 0:
        """Start a simple HTTP liveness probe on the given port."""
        server = HTTPServer(('0.0.0.0', port), HealthHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logging.info(f"Liveness probe running on port {port}.")
        return thread
    else:
        logging.info("LIVENESS_PORT not set or invalid. Liveness probe not started.")
        return None
    