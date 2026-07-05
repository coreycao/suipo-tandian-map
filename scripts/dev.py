"""本地编辑 + 一键发布服务器。

起一个 http 服务托管本地 editor.html，并暴露 POST /publish：
写入 data/manual_overrides.json -> 重建 index.html -> git add/commit/push。
GitHub Pages 随后自动部署。

用法:
  python3 scripts/dev.py            # 起服务并自动 push（默认）
  python3 scripts/dev.py --no-push  # 只写文件 + 构建 + commit，不 push（本地预览）
  SUIPO_NO_PUSH=1 python3 scripts/dev.py   # 等价于 --no-push

然后浏览器打开 http://localhost:8766/ ，编辑后点「🚀 一键发布」。
"""
import http.server
import json
import os
import socketserver
import subprocess
import sys
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EDITOR_HTML = os.path.join(ROOT, "editor.html")
BUILD_SITE = os.path.join(HERE, "build_site.py")
OVERRIDES_PATH = os.path.join(ROOT, "data", "manual_overrides.json")
PORT = int(os.environ.get("SUIPO_PORT", "8766"))
NO_PUSH = ("--no-push" in sys.argv) or (os.environ.get("SUIPO_NO_PUSH") == "1")
COMMIT_MSG_PREFIX = "Update shop data via local editor"


def run(cmd, **kw):
    """跑子进程，失败抛 CalledProcessError（含 stderr）。"""
    return subprocess.run(cmd, check=True, cwd=ROOT, capture_output=True, text=True, **kw)


def publish(overrides):
    """写 overrides -> 重建 index.html -> git add/commit/push。返回 dict 结果。"""
    n = len(overrides)
    # 1) 写人工补全文件
    with open(OVERRIDES_PATH, "w", encoding="utf-8") as f:
        json.dump(overrides, f, ensure_ascii=False, indent=2)
    # 2) 重建公开 index.html（烘焙 overrides）
    r = run([sys.executable, BUILD_SITE])
    build_log = r.stdout.strip()
    # 3) git add + commit + push
    pushed = False
    git_msg = ""
    run(["git", "add", "data/manual_overrides.json", "index.html"])
    c = subprocess.run(["git", "commit", "-m", f"{COMMIT_MSG_PREFIX} ({n} overrides)"],
                       cwd=ROOT, capture_output=True, text=True)
    if c.returncode != 0 and "nothing to commit" not in (c.stdout + c.stderr) and "no changes" not in (c.stdout + c.stderr):
        raise RuntimeError("git commit 失败：" + (c.stderr or c.stdout).strip())
    if not NO_PUSH:
        p = subprocess.run(["git", "push"], cwd=ROOT, capture_output=True, text=True)
        if p.returncode != 0:
            git_msg = (p.stderr or p.stdout).strip()
            raise RuntimeError("git push 失败：" + git_msg)
        pushed = True
    return {"ok": True, "applied": n, "pushed": pushed, "no_push": NO_PUSH, "build": build_log}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):  # 安静日志
        pass

    def _send(self, code, body=b"", ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if "text" in ctype or "json" in ctype else ""))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json")

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/editor.html"):
            try:
                with open(EDITOR_HTML, "rb") as f:
                    data = f.read()
            except FileNotFoundError:
                self._send(404, b"editor.html not built. Run: python3 scripts/build_site.py --editor", "text/plain")
                return
            self._send(200, data, "text/html")
        elif path == "/status":
            self._json({"ok": True, "no_push": NO_PUSH})
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/publish":
            self._send(404, b"not found", "text/plain")
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            overrides = json.loads(raw or b"{}")
            if not isinstance(overrides, dict):
                raise ValueError("body 必须是 {bvid: {field:value}} 对象")
            result = publish(overrides)
            self._json(result)
        except subprocess.CalledProcessError as e:
            self._json({"ok": False, "error": (e.stderr or e.stdout or str(e)).strip()[-500:]}, 500)
        except Exception as e:
            self._json({"ok": False, "error": str(e)}, 500)


def ensure_editor_built():
    """启动时保证 editor.html 最新。"""
    if not os.path.exists(EDITOR_HTML):
        run([sys.executable, BUILD_SITE, "--editor"])
    else:
        run([sys.executable, BUILD_SITE, "--editor"])  # 总是刷新，确保数据最新


def main():
    ensure_editor_built()
    mode = "本地预览（--no-push，不推送）" if NO_PUSH else "完整发布（构建+推送）"
    print(f"\n  隋坡探店地图 · 本地编辑器  [{mode}]")
    print(f"  打开： http://localhost:{PORT}/")
    print("  编辑后点「🚀 一键发布」。Ctrl+C 退出。\n")
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
