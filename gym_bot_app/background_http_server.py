import http
import logging
import threading
from http.server import HTTPServer


class HTTPHandler(http.server.SimpleHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.end_headers()


def run_simple_http_server(logger: logging.Logger, server: HTTPServer, port=8080):
    logger.info('Starting simple HTTP server on port %s', port)
    try:
        server.serve_forever()
    except:
        pass


def run_simple_http_server_on_background(logger: logging.Logger, should_run_simple_http_server: bool):
    server = None
    http_server_thread = None

    if should_run_simple_http_server:
        port = 8080
        server = HTTPServer(("0.0.0.0", port), HTTPHandler)
        http_server_thread = threading.Thread(target=run_simple_http_server, kwargs={
            'logger': logger,
            'server': server,
            'port': port
        })
        http_server_thread.start()

    def close_http_server_callback():
        if should_run_simple_http_server:
            logger.info('Closing HTTP server')
            server.server_close()
            http_server_thread.join()
            logger.info('Closed HTTP server')

    return close_http_server_callback
