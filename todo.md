# TODO

Lista rzeczy do dodania / ustalenia. Miejsca w kodzie oznaczone są komentarzem `# TODO`
(`grep -rn TODO backend/app`).

## Limity do ustalenia

Wartości w kodzie są tymczasowe – do ustalenia z zespołem / urzędem.

| Limit | Obecnie | Gdzie | Uwagi |
|---|---|---|---|
| `short_desc` – długość opisu wniosku w kalendarzu | 500 znaków | `backend/app/schemas.py` (`SHORT_DESC_MAX`) | TODO z `APIDOC.md` |
| `initials` – długość inicjałów urzędnika | 5 znaków | `backend/app/schemas.py` (`INITIALS_MAX`) | |
| `prompt` – długość zapytania urzędnika | 20 000 znaków | `backend/app/schemas.py` (`PROMPT_MAX`) | |
| `context` – liczba dokumentów po OCR w jednym zapytaniu | 50 | `backend/app/schemas.py` (`CONTEXT_ITEMS_MAX`) | |
| `context` – długość jednego dokumentu po OCR | 200 000 znaków | `backend/app/schemas.py` (`CONTEXT_ITEM_MAX`) | pilnować okna kontekstu modelu (DeepSeek: 64k–128k tokenów) |
| Tytuł wątku | 60 znaków | `backend/app/llm_client.py` (`TITLE_MAX`) | |
| Wejście do generowania tytułu | 2000 znaków pytania + 2000 odpowiedzi | `backend/app/llm_client.py` (`TITLE_INPUT_MAX`) | |
| RAG – liczba zwracanych fragmentów (`top_k`) | 5 | `config.toml` `[rag]` | |
| RAG – rozmiar fragmentu (`chunk_size`) | 1200 znaków | `config.toml` `[rag]` | zależny od modelu embeddingów |
| RAG – zakładka fragmentów (`chunk_overlap`) | 200 znaków | `config.toml` `[rag]` | |
| RAG – maks. rund wywołań narzędzi (`max_tool_rounds`) | 3 | `config.toml` `[rag]` | koszt / czas odpowiedzi |
| RAG – długość `snippet` w `sources` | 300 znaków | `backend/app/rag.py` (`SNIPPET_LEN`) | |
| Timeout LLM | 120 s | `config.toml` `[llm]` | |
| Timeout embeddingów | 30 s | `config.toml` `[rag.embeddings]` | |
| Rozmiar wgrywanego pliku | – | – | do ustalenia razem z serwerem plików |
| Rate limiting na użytkownika | – | – | do ustalenia razem z autoryzacją |

## Serwer plików z OCR jako źródło dla RAG (w stylu Google Drive)

Osobna usługa przechowywania dokumentów, z której RAG może wyszukiwać i cytować pliki jako źródła.

- [ ] Usługa plików: upload / download / lista / foldery (np. per wniosek, per wydział), wersjonowanie
- [ ] Storage: MinIO / S3-compatible albo dysk lokalny w kontenerze
- [ ] Model OCR po stronie serwera (np. Tesseract / PaddleOCR / docTR / model VLM) – PDF, skany, zdjęcia, DOCX
- [ ] Pipeline: upload → OCR → anonimizacja → chunking → embeddingi → indeks RAG
- [ ] Narzędzie dla LLM `search_files(query)` obok `search_conversations` + `read_file(file_id, page)` do pobrania pełnego fragmentu
- [ ] Źródła w odpowiedzi: `sources` z `file_id`, nazwą pliku, stroną – frontend linkuje do podglądu dokumentu
- [ ] Zasilenie przykładowymi wnioskami i odpowiedziami (`Hacknation 2026 - UMB/Przykładowe wnioski i odpowiedzi`) oraz podstawami prawnymi
- [ ] Uprawnienia do plików (kto widzi jakie dokumenty), log dostępu
- [ ] Reindeksacja po zmianie pliku / modelu OCR / modelu embeddingów
- [ ] Ustalić relację z obecnym OCR po stronie użytkownika (`context` w `POST /llm/request`)

## RAG

- [ ] Anonimizacja przed indeksowaniem – dane osobowe z jednej sprawy nie mogą trafiać do innej (`backend/app/rag.py`)
- [ ] Wybór modelu embeddingów (DeepSeek ich nie udostępnia) – np. lokalnie przez Ollama: `nomic-embed-text`, `bge-m3`, `multilingual-e5`
- [ ] Indeks wektorowy przy większej skali (sqlite-vec / pgvector) zamiast liczenia cosinusa w Pythonie
- [ ] Polski stemming / lematyzacja (np. Morfeusz, stempel) zamiast obcinania słów do prefiksu
- [ ] Reindeksacja (endpoint / komenda CLI) po zmianie modelu embeddingów lub `chunk_size`
- [ ] Zapisywanie `sources` przy wiadomości, żeby `GET /llm/{thread_id}` też je zwracał
- [ ] Usuwanie wątku → usuwanie z indeksu
- [ ] Ograniczenie wyszukiwania do wątków, do których użytkownik ma dostęp (po dodaniu autoryzacji)
- [ ] Ewaluacja jakości wyszukiwania na przykładowych wnioskach
- [ ] Struktura wydziałów UM Bydgoszczy (z BIP) jako źródło RAG – do wskazywania ścieżki

## API

- [ ] `PUT/PATCH /calendar/{id}` (zmiana statusu, `response_date`), `DELETE /calendar/{id}`
- [ ] Automatyczne wyliczanie `due_date` (14 dni od wpływu, art. 13 ust. 1 UDIP; przedłużenie do 2 mies.)
- [ ] Przypomnienia o zbliżających się terminach (w kalendarzu – bez automatycznej wysyłki na zewnątrz)
- [ ] `DELETE /llm/{thread_id}`, zmiana tytułu wątku
- [ ] Paginacja `GET /llm/all`, `GET /llm/{thread_id}`, `GET /calendar`
- [ ] Streaming odpowiedzi LLM (SSE)
- [ ] Osobny endpoint anonimizacji dokumentu
- [ ] Status RAG / embeddingów w `GET /llm/health`
- [ ] Ujednolicone formaty błędów

## Baza danych

- [ ] Opisać schemat w `backend/docs/DBDOC.md` (obecny SQLite w `backend/app/storage.py` jest tymczasowy)
- [ ] Migracje (Alembic) / decyzja SQLite vs PostgreSQL
- [ ] Szyfrowanie danych (in transit – TLS; at rest – do ustalenia)
- [ ] Asynchroniczny driver / pula połączeń przy większym ruchu
- [ ] Polityka retencji rozmów i danych osobowych (RODO)

## Bezpieczeństwo i autoryzacja

- [ ] Autoryzacja urzędników (np. SSO / LDAP urzędu, JWT)
- [ ] Role i uprawnienia (urzędnik, kierownik, admin)
- [ ] Przypisanie wątków i wniosków do użytkownika (`initials` z konta, nie z body)
- [ ] CORS dla frontendu
- [ ] Rate limiting
- [ ] Logi audytowe (kto, kiedy, jakie zapytanie) bez danych osobowych w logach
- [ ] Ochrona przed prompt injection z treści wgrywanych dokumentów

## LLM

- [ ] Testy na prawdziwym DeepSeeku (function calling, tytuły)
- [ ] Lokalny model do testów (Ollama) – sprawdzić obsługę function calling, w razie braku `rag.mode = "auto"`
- [ ] Szablony pism (projekt odpowiedzi, wezwanie do doprecyzowania, kwerenda do wydziału, przedłużenie terminu)
- [ ] Liczenie tokenów i przycinanie historii długich wątków

## Infrastruktura

- [ ] Dockerfile + docker-compose (backend, baza, serwer plików, OCR, Ollama)
- [ ] CI: testy, lint (ruff), typy (mypy)
- [ ] `.gitignore` w katalogu głównym repo (obecnie pusty)
