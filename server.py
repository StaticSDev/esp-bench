#!/usr/bin/env python3
"""Сервер-бенчмарк для Render (free tier).

Те же ТРИ теста, что и esp_bench.ino — можно сравнивать напрямую:
  1) cpu_int — целочислой цикл 20 млн итераций
  2) sha256  — хеширование 8 МБ
  3) mem     — перезапись буфера 128 КБ x 200 = 25.6 МБ

Зависимости: только стандартная библиотека Python.
Команда запуска (Render Start Command):  python server.py
Порт Render даёт через переменную окружения PORT.
"""
import hashlib
import json
import os
import platform
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CPU_N = 20_000_000
SHA_MB = 8
MEM_KB = 128
MEM_LOOPS = 200

# буферы готовим заранее, чтобы не мерить аллокацию входных данных
_SHA_DATA = b"esp32-c3 benchmark!" * (1024 * 1024 // 19 + 1)  # ~1 МБ
_SHA_DATA = (_SHA_DATA * SHA_MB)[: SHA_MB * 1024 * 1024]
_MEM_BUF = bytearray(MEM_KB * 1024)
_MEM_PAT = bytes((i * 7 + 3) & 0xFF for i in range(MEM_KB * 1024))


def bench_run():
    # 1) тот же цикл, что и на ESP: x = x*1664525 + 1013904223 (mod 2^32)
    t0 = time.perf_counter()
    x = 12345
    for _ in range(CPU_N):
        x = (x * 1664525 + 1013904223) & 0xFFFFFFFF
    cpu_ms = (time.perf_counter() - t0) * 1000.0

    # 2) sha256 8 МБ
    t0 = time.perf_counter()
    tag = hashlib.sha256(_SHA_DATA).hexdigest()
    sha_ms = (time.perf_counter() - t0) * 1000.0

    # 3) память: memcpy 128 КБ x 200
    buf = _MEM_BUF
    t0 = time.perf_counter()
    for _ in range(MEM_LOOPS):
        buf[:] = _MEM_PAT
    mem_ms = (time.perf_counter() - t0) * 1000.0

    return {
        "who": ("Render free" if os.environ.get("RENDER")
                else f"Локальный сервер ({platform.node()})")
               + f" {platform.system()} py{platform.python_version()} x{os.cpu_count()}",
        "cpu_int": {"n": CPU_N, "ms": round(cpu_ms, 1), "checksum": x},
        "sha256": {"mb": SHA_MB, "ms": round(sha_ms, 1),
                   "mbps": round(SHA_MB * 1000.0 / max(sha_ms, 0.1), 1),
                   "tag": int(tag[:8], 16)},
        "mem": {"mb": round(len(_MEM_PAT) * MEM_LOOPS / 1e6, 1),
                "ms": round(mem_ms, 1),
                "mbps": round(len(_MEM_PAT) * MEM_LOOPS * 1000.0 / max(mem_ms, 0.1) / 1e6, 1)},
        "heap_free_kb": None,
    }


def info():
    return {
        "os": f"{platform.system()} {platform.release()}",
        "cpu": platform.processor() or "unknown",
        "cores": os.cpu_count(),
        "python": platform.python_version(),
    }


INDEX = """<!doctype html><html><head><meta charset="utf-8"><title>Render-Bench</title>
<style>body{font-family:monospace;background:#0a0f0a;color:#33ff66;max-width:520px;margin:auto;padding:10px}
button{background:#000;color:#33ff66;border:1px solid #33ff66;padding:8px 16px}pre{white-space:pre-wrap;background:#000;padding:10px}</style>
</head><body><h2>Render-Bench</h2><button onclick="run()">ЗАПУСТИТЬ ТЕСТ</button><pre id="r">жду...</pre>
<script>async function run(){document.getElementById('r').textContent='считаю...';
try{let o=JSON.parse(await(await fetch('/run')).text());
let s='Тест           Время      Скорость\\n';
s+='CPU 20M итер: '+o.cpu_int.ms+' мс\\n';
s+='SHA256 8 МБ:  '+o.sha256.ms+' мс ('+o.sha256.mbps+' МБ/с)\\n';
s+='Память 26.2МБ: '+o.mem.ms+' мс ('+o.mem.mbps+' МБ/с)\\n\\n'+JSON.stringify(o);
document.getElementById('r').textContent=s;}catch(e){document.getElementById('r').textContent='ошибка: '+e;}}
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def _send(self, code, ctype, body):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index"):
            self._send(200, "text/html", INDEX)
        elif path == "/ping":
            self._send(200, "text/plain", "pong")
        elif path == "/run":
            self._send(200, "application/json", json.dumps(bench_run()))
        elif path == "/info":
            self._send(200, "application/json", json.dumps(info()))
        else:
            self._send(404, "text/plain", "not found")

    def log_message(self, *args):   # без спама в логи Render
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print(f"Render-Bench слушает 0.0.0.0:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
