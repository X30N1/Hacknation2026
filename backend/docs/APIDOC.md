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
- url_podgladu: str (ścieżka względem API, np. `/dokumenty/5/plik`; zapisany plik to wersja zanonimizowana)

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
- dokument_id: int | null (przestarzałe – dokument z `/wnioski/analiza`)

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

## Zapis dokumentów – tylko po anonimizacji
Oryginał wniosku lub innego dokumentu nie trafia do bazy ani na dysk. Przepływ:
1. `POST /wnioski/odczyt` albo `POST /dokumenty/odczyt` – serwer odczytuje tekst w pamięci (OCR)
   i nic nie zapisuje.
2. Urzędnik poprawia tekst we frontendzie, a `POST /anonimizacja` proponuje dane do zamazania.
3. Frontend zamazuje tekst i wysyła wynik jako plik `.txt` przez `POST /sprawy/{id}/dokumenty`.
   Przy rejestracji wniosku robi to po `POST /sprawy`.

Zapisany dokument ma więc zawsze `metoda = "RECZNA"`, a `GET /dokumenty/{id}/plik` zwraca
zanonimizowany `.txt`.

### Obiekt Odczyt
- nazwa_pliku: str
- metoda: "DOCX" | "PDF_TEXT" | "OCR" | "RECZNA"
- ocr_pewnosc: float | null (0–1, tylko OCR)
- tekst: str

## POST /dokumenty/odczyt
multipart/form-data: `plik` (PDF, DOCX lub TXT; 415 inny format, 413 za duży).
Odczytuje tekst (DOCX / warstwa tekstowa PDF / OCR skanu) **bez zapisu**. Zwraca Odczyt.

## POST /wnioski/odczyt
Działa jak `POST /dokumenty/odczyt` i dodatkowo proponuje dane sprawy. Niczego nie zapisuje.
Zwraca:
- odczyt: Odczyt
- propozycja: { znak, data_wplywu, wnioskodawca, przedmiot }. `znak` pochodzi z nazwy pliku
  lub treści, a w ich braku jest to kolejny numer w roku. `wnioskodawca` i `przedmiot`
  pochodzą z LLM, gdy jest dostępny. Propozycja służy też do anonimizacji: frontend przekazuje
  `wnioskodawca` do `POST /anonimizacja`.

## POST /sprawy/{id}/dokumenty
multipart/form-data: `plik`, `rodzaj` (domyślnie "INNE"), `wydzial` (opcjonalnie).
Frontend wysyła tu wyłącznie zanonimizowany `.txt`, ale serwer tego nie weryfikuje.
Zwraca 201 + Dokument.

## POST /wnioski/analiza (przestarzałe)
**Zapisuje oryginał przed anonimizacją** – nie używać, zastępuje go `POST /wnioski/odczyt`.
multipart/form-data: `plik`. Zwraca `{ dokument: Dokument (sprawa_id = null), propozycja }`.
Dokument przypisuje się do sprawy przez `dokument_id` w `POST /sprawy`.

## PATCH /dokumenty/{id}
Body JSON: `{ "tekst": str }` – ręczna poprawka tekstu (np. po niepewnym OCR). Zwraca Dokument.

## GET /dokumenty/{id}/plik
Oryginalny plik dokumentu.

---

# Anonimizacja

System podpowiada, które fragmenty urzędnik powinien zamazać przed wysłaniem dokumentu.
Zwraca tylko **propozycje**: decyzję podejmuje urzędnik, a backend niczego nie zamazuje
ani nie zapisuje. Zamazanie wykonuje frontend (`AnonimizacjaPodglad.jsx`) przed zapisem
dokumentu – patrz „Zapis dokumentów – tylko po anonimizacji”.

Źródła propozycji (`zrodlo`):
- `WZORZEC` – wyrażenia regularne: PESEL i NIP (z sumą kontrolną), e-mail, telefon,
  rachunek, dowód, adres, kod pocztowy z miejscowością, data urodzenia, numer rejestracyjny,
  księga wieczysta, imię i nazwisko po „Pan/Pani/Wnioskodawca”.
- `SPRAWA` – wnioskodawca zapisany w sprawie, wyszukany w treści, także samo nazwisko
  w odmianie (Kowalski → Kowalskiego). Osoby prawne (fundacja, sp. z o.o., redakcja…) są pomijane.
- `LLM` – imiona i nazwiska bez kontekstu, dane wrażliwe, sytuacja rodzinna i majątkowa,
  tajemnice. Lista danych do anonimizacji jest w `app/prompts.py` (`ANONYMIZED_DATA`).
  Model dostaje tekst dokumentu, więc na produkcji działa **wyłącznie lokalny model**.
  Wyłącza się to w `config.toml`: `[anonimizacja] llm = false`. W trybie echo działają tylko
  wzorce, a w `uwagi` pojawia się ostrzeżenie.

### Obiekt Propozycje
```json
{
  "fragmenty": [
    { "start": 13, "end": 25, "kategoria": "IMIE_NAZWISKO", "etykieta": "Imię i nazwisko",
      "tekst": "Jan Kowalski", "zrodlo": "WZORZEC", "powod": null }
  ],
  "llm_uzyty": true,
  "uwagi": []
}
```
- `start` i `end` to zakres znaków w tekście dokumentu (`tekst[start:end] == fragment.tekst`).
  Fragmenty są posortowane rosnąco i nie nakładają się: przy kolizji wygrywa dłuższy zakres,
  a przy równych zakresach kolejno WZORZEC, SPRAWA, LLM.
  Indeksy są w znakach Unicode; dla polskiego tekstu są równe indeksom JS.
- `kategoria` przyjmuje jedną z wartości: `IMIE_NAZWISKO`, `PESEL`, `NIP`, `DOWOD`,
  `DATA_URODZENIA`, `ADRES`, `TELEFON`, `EMAIL`, `KONTO`, `POJAZD`, `KSIEGA_WIECZYSTA`,
  `DANE_WRAZLIWE`, `SYTUACJA_OSOBISTA`, `TAJEMNICA`, `INNE`. `etykieta` to jej polska nazwa.
- `powod` – krótkie uzasadnienie (od LLM albo „wnioskodawca w sprawie”).
- `llm_uzyty` – czy model sprawdzał tekst.
- `uwagi` – ostrzeżenia dla urzędnika, np. „model niedostępny – tylko wzorce” albo
  „dokument za długi – model sprawdził pierwsze N znaków”.

## GET /dokumenty/{id}/anonimizacja
Nie jest już używany przez frontend, bo dokumenty zapisują się po anonimizacji.
Propozycje dla zapisanego dokumentu, z wnioskodawcą sprawy, do której dokument należy.
Query: `llm` (bool, domyślnie `true`), `false` oznacza tylko wzorce.
Zwraca obiekt Propozycje. Błąd 404 oznacza brak dokumentu.

## POST /anonimizacja
Propozycje dla dowolnego tekstu, np. kontekstu OCR przed wysłaniem do asystenta albo
projektu pisma.
Body JSON: `{ "tekst": str, "wnioskodawca": str | null, "llm": bool = true }`.
Zwraca obiekt Propozycje. Błąd 422 oznacza błędne body.

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
