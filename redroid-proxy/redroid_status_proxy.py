#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAA redroid 状态查询代理（宿主机侧）
--------------------------------------
最小权限设计：只暴露「查询容器运行状态」一个能力，不提供任何启停/删除操作。

监听 172.17.0.1:18001（仅 docker bridge 网关，外网/局域网不可达）

接口：
  GET /inspect?name=<容器名>
  返回 JSON: {"ok":true,"status":"running","running":true} 或 {"ok":false,"error":"..."}

仅接受白名单内的容器名（默认允许名字里含 redroid 的容器）。
"""
import json
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

LISTEN_HOST = "172.17.0.1"
LISTEN_PORT = 18001

# 只允许查询这些容器（按名称正则白名单），避免被拿来探测宿主机上其他容器
ALLOW_PATTERNS = [
    re.compile(r"redroid", re.I),
    re.compile(r"^maa-web(-test)?$"),   # 本项目容器；-test 为 v1.0.3 之前的旧名，留作过渡
]

# 单次 docker 调用超时
DOCKER_TIMEOUT = 5


def name_allowed(name: str) -> bool:
    return any(p.search(name) for p in ALLOW_PATTERNS)


class Handler(BaseHTTPRequestHandler):
    server_version = "redroid-status-proxy/1.0"

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/inspect":
            self._json(404, {"ok": False, "error": "not found"})
            return

        qs = parse_qs(parsed.query)
        name = (qs.get("name", [""])[0] or "").strip()
        if not name:
            self._json(400, {"ok": False, "error": "missing name"})
            return

        if not name_allowed(name):
            self._json(403, {"ok": False, "error": "container not allowed"})
            return

        try:
            result = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Status}}|{{.State.Running}}", name],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=DOCKER_TIMEOUT,
                check=False,
            )
        except subprocess.TimeoutExpired:
            self._json(200, {"ok": False, "error": "docker inspect 超时"})
            return
        except FileNotFoundError:
            self._json(200, {"ok": False, "error": "宿主机未找到 docker 命令"})
            return
        except Exception as exc:  # pragma: no cover - 兜底
            self._json(200, {"ok": False, "error": f"inspect 异常: {exc}"})
            return

        if result.returncode != 0:
            err = (result.stderr or "").strip()
            self._json(200, {"ok": False, "error": err or "docker inspect 失败"})
            return

        state = (result.stdout or "").strip()
        status, _, running = state.partition("|")
        self._json(
            200,
            {
                "ok": True,
                "status": status or "unknown",
                "running": running.strip().lower() == "true",
            },
        )

    def log_message(self, fmt: str, *args) -> None:  # 静音，避免刷日志
        sys.stderr.write("[redroid-proxy] " + (fmt % args) + "\n")


def main() -> None:
    httpd = HTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    sys.stderr.write(f"[redroid-proxy] listening on {LISTEN_HOST}:{LISTEN_PORT}\n")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
