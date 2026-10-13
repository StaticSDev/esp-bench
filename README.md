# Render-Bench — сервер для сравнения с ESP32-C3

Один файл, ноль зависимостей (только стандартная библиотека Python).
Те же три теста, что в `esp_bench.ino`: cpu_int 20M, sha256 8 МБ, mem 26.2 МБ.

## Как задеплоить на Render (бесплатно)

1. **GitHub:** создай публичный репозиторий и закинь туда `server.py`
   (именно с именем `server.py` в корне — будет просто).
2. **render.com** → регистрация (Google/GitHub).
3. **New + → Web Service** → подключи свой репозиторий.
4. Настройки:
   - Name: `esp-bench` (любое)
   - Runtime: **Python 3**
   - Build Command: *(пусто)*
   - Start Command: **`python server.py`**
   - Instance Type: **Free**
5. **Create Web Service** → ждёшь деплой (~2 мин).
6. Получаешь URL вида `https://esp-bench-xxxx.onrender.com`

## Проверка

Открой `https://твой-сервис.onrender.com/run` — должен вернуться JSON
с `"who":"Render free (...)"`. Или `.../` — страница с кнопкой теста.

Важно: бесплатный инстанс **засыпает** после простоя. Первый запрос после сна
будет медленным (30–60 с пробуждение) — это нормально, потом пингнёшь нормально.

## Запуск сравнения у себя

```
python3 bench_compare.py --render https://твой-сервис.onrender.com
```

ESP по кабелю (/dev/ttyACM0), сервер по интернету — в конце выведется таблица.
