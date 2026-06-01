"""端口可达性测试服务 — 在前端和后端端口启动简单 HTTP 服务，用于从外网测试连通性

使用方式:
  python3 test_ports.py

启动后从外网浏览器或 curl 访问:
  curl http://<服务器IP>:<前端端口>
  curl http://<服务器IP>:<后端端口>
"""

import http.server
import os
import threading
import socket


def load_env():
    """从 .env 文件读取端口配置"""
    defaults = {"FRONTEND_PORT": "30251", "BACKEND_PORT": "30252"}
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    defaults[key.strip()] = val.strip()
    return int(defaults["FRONTEND_PORT"]), int(defaults["BACKEND_PORT"])


class PortHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        port = self.server.server_address[1]
        hostname = socket.gethostname()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
        except Exception:
            ip = "unknown"

        message = (
            f"✅ 端口 {port} 可达！\n\n"
            f"主机名: {hostname}\n"
            f"内网 IP: {ip}\n"
            f"端口: {port}\n"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(message.encode())

    def log_message(self, format, *args):
        print(f"  [{self.server.server_address[1]}] {args[0]}")


def start_server(port):
    try:
        server = http.server.HTTPServer(("0.0.0.0", port), PortHandler)
        print(f"✅ 端口 {port} 已启动，等待外网访问测试")
        server.serve_forever()
    except PermissionError:
        print(f"❌ 端口 {port}: 权限不足")
    except OSError as e:
        print(f"❌ 端口 {port}: {e}")


if __name__ == "__main__":
    frontend_port, backend_port = load_env()

    print("=" * 50)
    print("端口可达性测试服务")
    print("=" * 50)
    print()
    print("从外网测试:")
    print(f"  curl http://<服务器IP>:{frontend_port}")
    print(f"  curl http://<服务器IP>:{backend_port}")
    print()
    print("按 Ctrl+C 停止\n")

    t1 = threading.Thread(target=start_server, args=(frontend_port,), daemon=True)
    t2 = threading.Thread(target=start_server, args=(backend_port,), daemon=True)
    t1.start()
    t2.start()

    try:
        t1.join()
        t2.join()
    except KeyboardInterrupt:
        print("\n已停止")
