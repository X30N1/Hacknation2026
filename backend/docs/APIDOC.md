# API backendu

- Frontend woła API z prefiksem `/api` (proxy Vite obcina go w trybie dev) – backend ścieżek bez prefiksu.
- Daty w sprawach: `RRRR-MM-DD` (ISO). Znacznik czasu w `/llm/*`: `GG-MM:DD-MM-RRRR`.
- Błędy: `{"blad": "komunikat po polsku", "detail": ...}` z kodem HTTP (404, 409, 413, 415, 422, 502).
- Interaktywna dokumentacja: `http://localhost:8000/docs`.

## GET /health

Stan aplikacji (frontend: plakietka „AI: …” i baner o zewnętrznym modelu).
- status: "ok"
- ok: bool
- dzis: str (RRRR-MM-DD, data serwera – według niej liczone są terminy)
- llm: obiekt
  - backend: str ("echo" | "deepseek" | "lokalny" | "zewnętrzny")
  - model: str
  - dostepny: bool
  - zewnetrzny: bool (true = dane wychodzą poza urząd)
  - detail: str | null

---

# Sprawy (kalendarz wniosków)

Termin, status i pilność **liczy backend** ze zdarzeń (`app/sprawy/terminy.py`):
14 dni od wpływu (art. 13 ust. 1 UDIP); wezwanie do doprecyzowania bez nowego terminu
wstrzymuje bieg; po otrzymaniu doprecyzowania – 14 dni od tej daty; przedłużenie – nowy termin
(powyżej 2 miesięcy od wpływu → flaga). Sprawy z importu xlsx są zamknięte i pokazują
wartości z arkusza „jak są”, a problemy opisują `flagi`.

### Obiekt Sprawa (lista)
- id: int
- znak: str (`BKS.IV.1431.<nr>.<rok>`)
- nr: int, rok: int
- zrodlo: "upload" | "import" | "demo"
- wnioskodawca: str
- przedmiot: str
- data_wplywu: str
- termin: str | null (null gdy wstrzymany)
- termin_wstrzymany: bool
- status: "NOWY" | "W_WYDZIALACH" | "DOPRECYZOWANIE" | "PRZEDLUZONA" | "PROJEKT_GOTOWY" | "WYSLANA" | "BEZ_ROZPOZNANIA"
- pilnosc: "PRZEKROCZONY" | "DZIS" | "JUTRO" | "WKROTCE" (≤ 3 dni) | "BRAK" | "ZAMKNIETA"
- pozostalo_dni: int | null
- przedluzenie_dni: int | null
- data_odpowiedzi: str | null
- inicjaly: str | null
- flagi: ARRAY { kod: str, opis: str, propozycja: str | null }

### Obiekt Sprawa (szczegóły) = lista +
- zdarzenia: ARRAY Zdarzenie
- dokumenty: ARRAY Dokument

### Obiekt Zdarzenie
- id: int
- typ: "REJESTRACJA" | "PRZEKAZANIE" | "ODP_WYDZIALU" | "WEZWANIE_DOPRECYZOWANIE" | "DOPRECYZOWANIE_OTRZYMANE" | "PRZEDLUZENIE" | "PROJEKT" | "WYSLANO" | "BEZ_ROZPOZNANIA"
- data: str
- nowy_termin: str | null
- payload: obiekt (np. `{"wydzialy": ["WGK"]}`)
- inicjaly: str | null

### Obiekt Dokument
- id: int
- sprawa_id: int | null (null do zatwierdzenia sprawy)
- rodzaj: str ("WNIOSEK", "ODP_WYDZIALU", … – wielkie litery)
- nazwa_pliku: str
- wydzial: str | null
- metoda: "DOCX" | "PDF_TEXT" | "OCR" | "RECZNA"
- ocr_pewnosc: float | null (0–1, tylko OCR)
- tekst: str
- url_podgladu: str (ścieżka względem API, np. `/dokumenty/5/plik`)

## GET /sprawy
Query (opcjonalnie): `rok` (int), `otwarte` (1/true – bez zamkniętych).
Zwraca ARRAY Sprawa (lista), od najstarszego wpływu.

## GET /sprawy/{id}
Zwraca Sprawa (szczegóły). 404 gdy brak.

## POST /sprawy
Body JSON:
- znak: str (wymagany, format jak wyżej; 409 gdy istnieje)
- data_wplywu: str (wymagana, nie z przyszłości)
- wnioskodawca: str, przedmiot: str, inicjaly: str | null
- dokument_id: int | null (dokument z `/wnioski/analiza` – zostaje przypisany do sprawy)

Zwraca 201 + Sprawa (szczegóły).

## PATCH /sprawy/{id}
Body JSON (dowolny podzbiór): wnioskodawca, przedmiot, inicjaly, data_wplywu.
Zwraca Sprawa (szczegóły).

## POST /sprawy/{id}/zdarzenia
Body JSON:
- typ: str (wymagany)
- data: str (wymagana; nie przed wpływem, nie z przyszłości)
- nowy_termin: str | null (wymagany dla PRZEDLUZENIE, później niż obecny termin)
- payload: obiekt (PRZEKAZANIE wymaga `wydzialy`: niepusta lista)
- inicjaly: str | null

Dozwolone przejścia (409 w pozostałych przypadkach i dla spraw z importu):

| typ | w statusie |
|---|---|
| PRZEKAZANIE | NOWY, W_WYDZIALACH, PRZEDLUZONA |
| ODP_WYDZIALU | W_WYDZIALACH, PRZEDLUZONA |
| WEZWANIE_DOPRECYZOWANIE | NOWY, W_WYDZIALACH |
| DOPRECYZOWANIE_OTRZYMANE | DOPRECYZOWANIE |
| PRZEDLUZENIE | NOWY, W_WYDZIALACH, PRZEDLUZONA |
| PROJEKT | W_WYDZIALACH, PRZEDLUZONA |
| WYSLANO | PROJEKT_GOTOWY |
| BEZ_ROZPOZNANIA | DOPRECYZOWANIE |

Zwraca 201 + Sprawa (szczegóły). Aplikacja niczego nie wysyła – zdarzenie tylko zapisuje, co zrobił urzędnik.

## POST /wnioski/analiza
multipart/form-data: `plik` (PDF, DOCX lub TXT; 415 inny format, 413 za duży).
Odczytuje tekst (DOCX / warstwa tekstowa PDF / OCR skanu) i proponuje dane sprawy.
Zwraca:
- dokument: Dokument (sprawa_id = null)
- propozycja: { znak, data_wplywu, wnioskodawca, przedmiot } (znak z nazwy pliku / treści albo kolejny numer w roku; wnioskodawca i przedmiot z LLM, gdy dostępny)

## POST /sprawy/{id}/dokumenty
multipart/form-data: `plik`, `rodzaj` (domyślnie "INNE"), `wydzial` (opcjonalnie).
Zwraca 201 + Dokument.

## PATCH /dokumenty/{id}
Body JSON: `{ "tekst": str }` – ręczna poprawka tekstu (np. po niepewnym OCR). Zwraca Dokument.

## GET /dokumenty/{id}/plik
Oryginalny plik dokumentu.

---

# Asystent LLM

Wiadomości w wątku numerowane są kolejno, łącznie dla obu stron rozmowy:
`message_id` = 1 (pytanie urzędnika), 2 (odpowiedź LLM), 3 (kolejne pytanie), …
Pole `msg_owner` mówi, kto napisał wiadomość: `"user"` (urzędnik) albo `"assistant"` (LLM).

## POST /llm/request

Czego się spodziewa (JSON):
 - thread_id: int (id wątku; -1 = nowy wątek, którego id wraca w odpowiedzi)
 - prompt: str (prośba bazowa użytkownika)
 - context: arr[str] (opcjonalnie; teksty dokumentów po OCR – dołączane do pytania dla LLM,
   zapisywane osobno od promptu)

Co zwraca:
 - thread_id: int (id wątku wiadomości)
 - message_id: int (numer kolejny tej wiadomości w wątku – dla odpowiedzi LLM zawsze parzysty)
 - msg_owner: str (zawsze "assistant")
 - content: str (odpowiedź od LLM)
 - timestamp: str (GG-MM:DD-MM-RRRR)
 - sources: ARRAY (fragmenty wcześniejszych rozmów użyte przez RAG, może być puste)
   - thread_id: int
   - message_id: int (numer wiadomości w wątku źródłowym)
   - msg_owner: str ("user" | "assistant" – kto napisał fragment)
   - title: str (tytuł wątku źródłowego)
   - snippet: str (fragment tekstu)
   - score: float (trafność)

Błędy: 404 – wątek nie istnieje, 422 – niepoprawne dane, 502 – błąd LLM.

## GET /llm/all

Co oczekuje:
nic
Co zwraca:
ARRAY
- id: int (id wątku)
- title: str (nazwa wątku generowana przez LLM z pierwszego pytania i odpowiedzi)
- create_date: str (GG-MM:DD-MM-RRRR, data pierwszej wiadomości wątku)

## GET /llm/health

Czego oczekuje:
nic
Co zwraca (HTTP 200 gdy OK / tryb echo, HTTP 503 gdy model niedostępny):
- status: str ("ok" | "echo" | "error")
- model: str (nazwa modelu)
- base_url: str (adres API LLM)
- latency_ms: int | null (czas odpowiedzi API modelu)
- detail: str | null (opis błędu)

## GET /llm/{thread_id}

Czego oczekuje:
ID wątku (404 gdy nie istnieje)

Co oddaje:
ARRAY – wszystkie wiadomości wątku (obie strony), w kolejności `message_id`
- message_id: int (numer kolejny wiadomości w wątku: 1, 2, 3, …)
- msg_owner: str ("user" – urzędnik | "assistant" – LLM)
- content: str (user: prompt urzędnika bez dołączonego kontekstu OCR; assistant: odpowiedź LLM)
- timestamp: str (GG-MM:DD-MM-RRRR)
