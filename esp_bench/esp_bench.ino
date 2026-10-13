// ESP-Bench: тест производительности ESP32-C3.
// Три теста, ОДИНАКОВЫЙ алгоритм что на сервере (см. render_bench/server.py):
//   1) cpu_int  — целочисловой цикл 20 млн итераций
//   2) sha256   — хеширование 8 МБ
//   3) mem      — перезапись буфера 128 КБ x 200 = 25.6 МБ
// Веб: точка "ESP-Bench" -> http://192.168.4.1  (кнопка "Запустить тест")
// Кабель: команда "run" в терминал печатает тот же JSON (его ест bench_compare.py)
#include <WiFi.h>
#include <WebServer.h>
#include "mbedtls/sha256.h"

WebServer srv(80);
static uint8_t memBuf[131072];   // 128 КБ буфера для теста памяти/хеша

String benchRun() {
  // --- 1) CPU: x = x * 1664525 + 1013904223, 20 млн раз (uint32 переполняется) ---
  uint32_t t0 = micros();
  uint32_t x = 12345;
  for (uint32_t i = 0; i < 20000000UL; i++) x = x * 1664525UL + 1013904223UL;
  float cpuMs = (micros() - t0) / 1000.0f;

  // --- 2) SHA256 8 МБ (64 блока по 128 КБ), streaming mbedTLS ---
  mbedtls_sha256_context ctx;
  mbedtls_sha256_init(&ctx);
  mbedtls_sha256_starts(&ctx, 0);
  memset(memBuf, 0xA5, sizeof(memBuf));
  t0 = micros();
  for (int k = 0; k < 64; k++) mbedtls_sha256_update(&ctx, memBuf, sizeof(memBuf));
  uint8_t hash[32];
  mbedtls_sha256_finish(&ctx, hash);
  float shaMs = (micros() - t0) / 1000.0f;
  mbedtls_sha256_free(&ctx);
  uint32_t shaTag; memcpy(&shaTag, hash, 4);

  // --- 3) Память: memset 128 КБ x 200 = 25.6 МБ перезаписи ---
  t0 = micros();
  for (int k = 0; k < 200; k++) memset(memBuf, (uint8_t)(k & 0xFF), sizeof(memBuf));
  float memMs = (micros() - t0) / 1000.0f;

  char out[700];
  snprintf(out, sizeof(out),
    "{\"who\":\"ESP32-C3 @%uMHz\","
    "\"cpu_int\":{\"n\":20000000,\"ms\":%.1f,\"checksum\":%u},"
    "\"sha256\":{\"mb\":8,\"ms\":%.1f,\"mbps\":%.1f,\"tag\":%u},"
    "\"mem\":{\"mb\":26.2,\"ms\":%.1f,\"mbps\":%.1f},"
    "\"heap_free_kb\":%u}",
    (unsigned)getCpuFrequencyMhz(),
    cpuMs, (unsigned)x,
    shaMs, (float)8000.0f / (shaMs > 0.1f ? shaMs : 0.1f), (unsigned)shaTag,
    memMs, (float)26214.4f / (memMs > 0.1f ? memMs : 0.1f),
    (unsigned)(ESP.getFreeHeap() / 1024));
  return String(out);
}

const char PAGE[] PROGMEM = R"rawliteral(
<!doctype html><html><head><meta charset="utf-8" name="viewport" content="width=device-width,initial-scale=1">
<title>ESP-Bench</title><style>body{font-family:monospace;background:#0a0f0a;color:#33ff66;max-width:520px;margin:auto;padding:10px}
button{background:#000;color:#33ff66;border:1px solid #33ff66;padding:8px 16px}pre{white-space:pre-wrap;background:#000;padding:10px;border:1px solid #1a5c2e}</style></head><body>
<h2>ESP-Bench</h2><button onclick="run()">ЗАПУСТИТЬ ТЕСТ</button><pre id="r">жду...</pre>
<script>async function run(){document.getElementById('r').textContent='считаю (1-2 сек)...';
try{let j=await(await fetch('/run')).text();
let o=JSON.parse(j);let s='Тест          Время      Скорость\n';
s+='CPU 20M итер: '+o.cpu_int.ms+' мс\n';
s+='SHA256 8 МБ:  '+o.sha256.ms+' мс ('+o.sha256.mbps+' МБ/с)\n';
s+='Память 26.2МБ: '+o.mem.ms+' мс ('+o.mem.mbps+' МБ/с)\n';
s+='Свободно RAM: '+o.heap_free_kb+' КБ\n\n'+j;
document.getElementById('r').textContent=s;}catch(e){document.getElementById('r').textContent='ошибка: '+e;}}
</script></body></html>)rawliteral";

void setup() {
  Serial.begin(115200);
  WiFi.mode(WIFI_AP);
  WiFi.softAP("ESP-Bench");
  srv.on("/", []() { srv.send_P(200, "text/html", PAGE); });
  srv.on("/ping", []() { srv.send(200, "text/plain", "pong"); });
  srv.on("/run", []() { srv.send(200, "application/json", benchRun()); });
  srv.on("/info", []() {
    String j = "{\"chip\":\"" + String(ESP.getChipModel()) + "\",\"freq_mhz\":" +
               String(getCpuFrequencyMhz()) + ",\"heap_free_kb\":" +
               String(ESP.getFreeHeap() / 1024) + "}";
    srv.send(200, "application/json", j);
  });
  srv.begin();
  Serial.println("ESP-Bench готов. Сеть: ESP-Bench (http://192.168.4.1). По кабелю: run / info / help");
}

void loop() {
  srv.handleClient();
  if (Serial.available()) {
    String s = Serial.readStringUntil('\n');
    s.trim();
    if (s == "run") Serial.println(benchRun());
    else if (s == "info") Serial.println("{\"chip\":\"" + String(ESP.getChipModel()) + "\",\"freq_mhz\":" + String(getCpuFrequencyMhz()) + "}");
    else if (s == "help") Serial.println("Команды: run, info, help");
    else if (s.length()) Serial.println("Неизвестно. help");
  }
}
