#!/usr/bin/env python3
"""Сравнение производительности: ESP32-C3 против сервера (например, Render free).

ESP читается ПО КАБЕЛЮ (команда run), сервер — по HTTP/HTTPS.
Одинаковые тесты: cpu_int 20M, sha256 8MB, mem 25.6MB.

Запуск:
  python3 bench_compare.py --render https://ваш-сервис.onrender.com
  python3 bench_compare.py --render http://127.0.0.1:8080     # локальный тест
  python3 bench_compare.py --render URL --esp-url http://192.168.4.1  # ESP по вебу
"""
import argparse
import json
import os
import select
import sys
import termios
import time
import urllib.request

PORT = "/dev/ttyACM0"


def esp_serial_run(port=PORT, timeout=60):
    """Просит плату выполнить run и возвращает JSON."""
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY)
    a = termios.tcgetattr(fd)
    iflag, oflag, cflag, lflag, ispeed, ospeed, cc = a
    iflag &= ~(termios.IGNBRK | termios.BRKINT | termios.PARMRK | termios.ISTRIP |
               termios.INLCR | termios.IGNCR | termios.ICRNL | termios.IXON)
    oflag &= ~termios.OPOST
    lflag &= ~(termios.ECHO | termios.ECHONL | termios.ICANON | termios.ISIG | termios.IEXTEN)
    cflag &= ~(termios.CSIZE | termios.PARENB)
    cflag |= termios.CS8 | termios.CREAD | termios.CLOCAL
    cc = list(cc); cc[termios.VMIN] = 0; cc[termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW,
                      [iflag, oflag, cflag, lflag, termios.B115200, termios.B115200, cc])
    time.sleep(2.6)                      # плата перезагружается при открытии порта
    os.write(fd, b"run\n")
    buf = ""
    end = time.time() + timeout
    try:
        while time.time() < end:
            r, _, _ = select.select([fd], [], [], 0.5)
            if fd in r:
                buf += os.read(fd, 8192).decode("utf-8", "replace")
            # JSON может прийти кусками — ищем начало и пробуем разобрать,
            # raw_decode вернёт объект, как только он станет полным
            i = buf.find('{"who"')
            if i < 0:
                i = buf.find('{"cpu_int"')
            if i >= 0:
                try:
                    obj, _ = json.JSONDecoder().raw_decode(buf[i:])
                    if "cpu_int" in obj:
                        return obj
                except ValueError:
                    pass   # ещё не дописали, ждём следующий кусок
    finally:
        os.close(fd)
    raise RuntimeError("ESP не вернул JSON за %dс (запущен ли esp_bench?)" % timeout)


def http_json(url, timeout=60):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def ping(url, n=5):
    best = None
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                r.read()
        except Exception:
            return None
        dt = (time.perf_counter() - t0) * 1000
        best = dt if best is None else min(best, dt)
    return best


def fmt(ms):
    return "-" if ms is None else f"{ms:.1f} мс"


def row(name, a, b, lower_is_better=True, fmt_a=None, fmt_b=None):
    fa = fmt_a(a) if fmt_a else fmt(a)
    fb = fmt_b(b) if fmt_b else fmt(b)
    win = "-"
    if a is not None and b is not None:
        if lower_is_better:
            win = "ESP" if a < b else "Сервер"
            ratio = max(a, b) / max(min(a, b), 0.001)
            win += f" x{ratio:.1f}"
        else:   # например МБ/с — больше лучше
            win = "ESP" if a > b else "Сервер"
            ratio = max(a, b) / max(min(a, b), 0.001)
            win += f" x{ratio:.1f}"
    print(f"{name:<26} {fa:>12} {fb:>14}   {win}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", required=True, help="URL сервера, напр. https://xxx.onrender.com")
    ap.add_argument("--esp-url", help="Если плата в сети: http://192.168.4.1 (иначе читаем по кабелю)")
    ap.add_argument("--serial", default=PORT, help="Порт платы (по умолчанию /dev/ttyACM0)")
    a = ap.parse_args()

    print("1/3 ESP: запускаю тесты на плате...")
    if a.esp_url:
        esp = http_json(a.esp_url.rstrip("/") + "/run")
    else:
        esp = esp_serial_run(a.serial)
    print("   готово:", esp["who"])

    print("2/3 Сервер: запускаю те же тесты...")
    srv = http_json(a.render.rstrip("/") + "/run")
    print("   готово:", srv["who"])

    print("3/3 Пинг (лучший из 5)...")
    ep = ping((a.esp_url or "http://192.168.4.1") + "/ping") if a.esp_url else None
    sp = ping(a.render.rstrip("/") + "/ping")

    print()
    print("=" * 68)
    print(f"{'Метрика':<26} {'ESP32-C3':>12} {'Сервер':>14}   Победитель")
    print("-" * 68)
    row("CPU цикл 20M (меньше=лучше)",
        esp["cpu_int"]["ms"], srv["cpu_int"]["ms"])
    row("SHA256 8 МБ (меньше=лучше)",
        esp["sha256"]["ms"], srv["sha256"]["ms"])
    row("SHA256 скорость, МБ/с",
        esp["sha256"].get("mbps"), srv["sha256"].get("mbps"),
        lower_is_better=False,
        fmt_a=lambda v: f"{v:.1f}" if v else "-",
        fmt_b=lambda v: f"{v:.1f}" if v else "-")
    row("Память 26.2 МБ (меньше=лучше)",
        esp["mem"]["ms"], srv["mem"]["ms"])
    if ep is not None or sp is not None:
        row("HTTP ping (меньше=лучше)", ep, sp)
    print("=" * 68)
    print("Замечания:")
    print("  • CPU-цикл честный для обоих, но на сервере цикл на Python")
    print("    (интерпретатор добавляет накладные расходы — это нормально).")
    print("  • SHA256 у обоих в C, тут чисто меряемся тактовой частотой.")
    print("  • Пинг сервера включает интернет; ESP пинг — только если --esp-url.")


if __name__ == "__main__":
    main()
