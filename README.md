# Hacknation2026

# Temat
[Urząd miasta Bydgoszcz] - Inteligentny asystent urzędnika

# Uruchomienie

## W urzędzie (Docker)
```bash
docker compose run --rm ollama-pobierz   # jednorazowo: model OCR glm-ocr (jedyny krok z internetem)
docker compose up --build                # http://localhost:8000
```
Obraz aplikacji: frontend, API i dane startowe – kalendarium xlsx, archiwum przykładowych pism
i podstawy prawne z paczki UMB. Skany rozpoznaje **GLM-OCR** w kontenerze Ollamy (sieć wewnętrzna,
bez internetu). Baza i dokumenty trwają w wolumenie `dane`, modele w wolumenie `modele`.

## Dewelopersko
```bash
cd backend && uv sync && uv run python -m app.seed --archiwum && uv run uvicorn main:app --reload
cd frontend && npm install && npm run dev   # http://localhost:5173 (proxy /api -> :8000)
```
OCR skanów lokalnie: zainstaluj Ollamę i `ollama pull glm-ocr` (backend łączy się z `http://localhost:11434`).
Zamiast Ollamy można użyć vLLM / SGLang: `[ocr] api = "openai"`, `base_url = "http://<serwer>:8080/v1"`.
Bez serwera OCR skany wracają z pustym tekstem do wpisania ręcznie.

# Logowanie
Przy pierwszym uruchomieniu powstaje konto **admin / admin**. Przy pierwszym logowaniu trzeba ustawić
własne hasło i drugi składnik: aplikację TOTP (Google/Microsoft Authenticator, Aegis…) albo klucz
sprzętowy FIDO2 (YubiKey itp.). Administrator w zakładce „Użytkownicy” dodaje i usuwa konta, ustawia
hasła tymczasowe (odblokowuje konto) i resetuje drugi składnik. Ustawienia: `[auth]` w `config.toml`.
Klucze sprzętowe działają tylko przez HTTPS albo na `localhost` – przy innym adresie ustaw `rp_id`
i `origins`, a za reverse proxy z TLS `cookie_secure = true`.

# Model językowy – działanie bez internetu
Aplikacja działa w pełni **bez modelu językowego**: OCR (GLM-OCR), kalendarz, wyszukiwanie w archiwum (SQLite FTS5),
wydziały z archiwum i słów kluczowych, projekt pisma z szablonu, anonimizacja wzorcami.
Model (API zgodne z OpenAI) dodaje: imiona, nazwiska i dane wrażliwe w anonimizacji, uzasadnione
propozycje wydziałów i redakcję projektu pisma.

- Na Hacknation: DeepSeek (`backend/config.toml`, wzór `config.example.toml`). Interfejs pokazuje
  czerwony baner, gdy model działa poza urzędem.
- Docelowo w urzędzie: model lokalny przez Ollamę, bez dostępu do internetu, np. **Qwen2.5 7B Instruct**
  (dobra obsługa polskiego i JSON, działa na pojedynczym GPU / mocnym CPU) albo polski **Bielik 11B**
  (SpeakLeash). Uruchomienie: jednorazowo `MODEL="glm-ocr qwen2.5:7b" docker compose run --rm ollama-pobierz`
  (jedyny krok z internetem), potem `docker compose up`, a w `config.toml`:
  `[llm] base_url = "http://ollama:11434/v1"`, `api_key = ""`, `model = "qwen2.5:7b"`.
  Ollama działa w wewnętrznej sieci `llm`: widzi tylko aplikację, bez internetu i bez opublikowanych portów.

# Jak to spełnia wymagania wyzwania
| Wymaganie | Gdzie |
|---|---|
| Wgrywanie PDF / Word / skanów | Nowy wniosek, Dokumenty w sprawie (OCR GLM-OCR) |
| Kalendarz wniosków | Kalendarz: tabela od najstarszego, dni do terminu, podświetlenie terminu dziś / jutro, wybór roku, widok miesiąca |
| Statusy a)–e) | Brak działań → Zapytania w wydziałach → Kwerenda (+dni) → Odpowiedź przygotowana → Wysłana |
| Anonimizacja | Każdy dokument przed zapisem: dane na szaro → po akceptacji na czarno; do bazy trafia tylko wersja zanonimizowana, serwer odrzuca niezamazany PESEL / dowód |
| Przeszukiwanie archiwum | Sprawa → „Podobne sprawy z archiwum”; Archiwum i wiedza → wyszukiwarka |
| Wskazywanie ścieżki | Sprawa → „Sugerowane wydziały” (lista jednostek z BIP UMB, uzasadnienie) |
| Projekt odpowiedzi | Odpowiedź wydziału – wgraj plik → Przygotuj projekt odpowiedzi → sprawdzenie → anonimizacja → .docx / .txt |
| „Uczenie się” na ustawach i archiwum | Archiwum i wiedza → baza wiedzy (dodawanie, usuwanie starych wersji) |
| Brak wysyłki i integracji | Aplikacja tylko zapisuje, co zrobił urzędnik; pliki pobiera on sam |
