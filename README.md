# Hacknation2026

# Temat
[Urząd miasta Bydgoszcz] - Inteligentny asystent urzędnika

# Uruchomienie

## W urzędzie (Docker)
```bash
docker compose up --build        # http://localhost:8000
```
Jeden obraz: frontend, API, OCR (Tesseract z językiem polskim) i dane startowe – kalendarium xlsx,
10 wniosków testowych z terminami względem dzisiejszej daty, archiwum przykładowych pism
i podstawy prawne z paczki UMB. Baza i dokumenty trwają w wolumenie `dane`.

## Dewelopersko
```bash
cd backend && uv sync && uv run python -m app.seed --archiwum && uv run uvicorn main:app --reload
cd frontend && npm install && npm run dev   # http://localhost:5173 (proxy /api -> :8000)
```
Windows: Tesseract z instalatora UB Mannheim (z językiem Polish) – backend znajdzie go także poza PATH.

# Model językowy – działanie bez internetu
Aplikacja działa w pełni **bez modelu**: OCR, kalendarz, wyszukiwanie w archiwum (SQLite FTS5),
wydziały z archiwum i słów kluczowych, projekt pisma z szablonu, anonimizacja wzorcami.
Model (API zgodne z OpenAI) dodaje: imiona, nazwiska i dane wrażliwe w anonimizacji, uzasadnione
propozycje wydziałów i redakcję projektu pisma.

- Na Hacknation: DeepSeek (`backend/config.toml`, wzór `config.example.toml`). Interfejs pokazuje
  czerwony baner, gdy model działa poza urzędem.
- Docelowo w urzędzie: model lokalny przez Ollamę, bez dostępu do internetu, np. **Qwen2.5 7B Instruct**
  (dobra obsługa polskiego i JSON, działa na pojedynczym GPU / mocnym CPU) albo polski **Bielik 11B**
  (SpeakLeash). Uruchomienie: `docker compose --profile ai up`, `docker compose exec ollama ollama pull qwen2.5:7b`,
  a w `config.toml`: `[llm] base_url = "http://ollama:11434/v1"`, `api_key = ""`, `model = "qwen2.5:7b"`.

# Jak to spełnia wymagania wyzwania
| Wymaganie | Gdzie |
|---|---|
| Wgrywanie PDF / Word / skanów | Nowy wniosek, Dokumenty w sprawie (OCR Tesseract) |
| Kalendarz wniosków | Kalendarz: tabela od najstarszego, dni do terminu, podświetlenie terminu dziś / jutro, wybór roku, widok miesiąca |
| Statusy a)–e) | Brak działań → Zapytania w wydziałach → Kwerenda (+dni) → Odpowiedź przygotowana → Wysłana |
| Anonimizacja | Każdy dokument przed zapisem: dane na szaro → po akceptacji na czarno; do bazy trafia tylko wersja zanonimizowana, serwer odrzuca niezamazany PESEL / dowód |
| Przeszukiwanie archiwum | Sprawa → „Podobne sprawy z archiwum”; Archiwum i wiedza → wyszukiwarka |
| Wskazywanie ścieżki | Sprawa → „Sugerowane wydziały” (lista jednostek z BIP UMB, uzasadnienie) |
| Projekt odpowiedzi | Odpowiedź wydziału – wgraj plik → Przygotuj projekt odpowiedzi → sprawdzenie → anonimizacja → .docx / .txt |
| „Uczenie się” na ustawach i archiwum | Archiwum i wiedza → baza wiedzy (dodawanie, usuwanie starych wersji) |
| Brak wysyłki i integracji | Aplikacja tylko zapisuje, co zrobił urzędnik; pliki pobiera on sam |

# Struktura
LLM - Wstępnie hostowany Deepseek, z możliwością zmiany API na lokalne (testy)

# Podział obowiązków
## Backend - Łukasz Wronka
Zakres obowiązków:
- Fastapi REST do
  - RAGA
  - BAZY DANYCH (dane szyfrowane in transit)
  - Autoryzacja
  - Security
- Konteneryzacja do dockera
- Testy i CI
## ????
