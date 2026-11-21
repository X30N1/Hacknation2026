# API backendu

- Frontend woła API z prefiksem `/api` (proxy Vite obcina go w trybie dev) – backend ścieżek bez prefiksu.
- Daty w sprawach: `RRRR-MM-DD` (ISO).
- Błędy: `{"blad": "komunikat po polsku", "detail": ...}` z kodem HTTP (404, 409, 413, 415, 422).
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
- zrodlo: "upload" | "import"
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

Treść wniosku zapisuje się osobno, po anonimizacji: `POST /sprawy/{id}/dokumenty` (rodzaj WNIOSEK).

Zwraca 201 + Sprawa (szczegóły).

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

Zapisany dokument ma więc zawsze `metoda = "RECZNA"`; `GET /dokumenty/{id}/docx` zwraca
jego zanonimizowany tekst jako plik Word.

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
Frontend wysyła tu wyłącznie zanonimizowany `.txt`. Serwer odrzuca (422) tekst z niezamazanym
numerem PESEL lub numerem dowodu – ostatnia linia obrony. Rodzaje używane przez frontend:
WNIOSEK, ODP_WYDZIALU (z `wydzial`), PROJEKT, ODPOWIEDZ, KWERENDA, WEZWANIE, INNE.
Zwraca 201 + Dokument.

## PATCH /dokumenty/{id}
Body JSON: `{ "tekst": str }` – ręczna poprawka tekstu (np. po niepewnym OCR). Ta sama blokada
PESEL / dowodu co przy zapisie. Zwraca Dokument.

## GET /dokumenty/{id}/docx
Tekst dokumentu jako plik Word (`Content-Disposition: attachment`).

---

# Archiwum, ścieżka, projekt odpowiedzi

Działa lokalnie (SQLite FTS5), model językowy jest opcjonalny.

## GET /sprawy/{id}/podobne?limit=5
Podobne sprawy: przedmiot + treść zanonimizowanych dokumentów, ranking FTS5 łączony przez RRF,
próg pokrycia ważonych (IDF) słów przedmiotu. Zwraca listę:
`{ id, znak, przedmiot, data_wplywu, status, wydzialy: [str], fragment: str, ma_odpowiedz: bool }`.
`fragment` zawiera trafione słowa w nawiasach kwadratowych: `…[odśnieżanie] ulic…`.

## GET /sprawy/{id}/wydzialy
`{ sugestie: [{ skrot, nazwa, uzasadnienie, zrodlo }], wszystkie: [{ skrot, nazwa }] }`.
`zrodlo`: `ARCHIWUM` (odpowiadał w podobnych sprawach) | `LLM` (wybór z zamkniętej listy) |
`SLOWA_KLUCZOWE`. Lista jednostek: BIP UM Bydgoszcz (wydziały i biura).

## POST /sprawy/{id}/projekt
Projekt pisma z odpowiedzi wydziałów (dokumenty ODP_WYDZIALU), z wzorem stylu z podobnych spraw
i podstawami z bazy wiedzy. **Niczego nie zapisuje.** Dane wnioskodawcy nie trafiają do modelu.
`{ tekst, llm_uzyty: bool, zrodla: [str], uwagi: [str] }`. Bez modelu – szablon pisma.

## GET /archiwum/szukaj?q=fraza
Sprawy, dokumenty spraw i baza wiedzy: `[{ sprawa_id, znak, dokument_id, nazwa_pliku, rodzaj, data, fragment }]`
(`rodzaj` = SPRAWA albo rodzaj dokumentu).

## Baza wiedzy
- `GET /wiedza` → `[{ id, rodzaj, nazwa_pliku, znaki, utworzono }]`
- `POST /wiedza` multipart `plik`, `rodzaj` (USTAWA | ZARZADZENIE | WZOR | ARCHIWUM) → 201 + Dokument (`sprawa_id = null`); blokada PESEL / dowodu
- `DELETE /wiedza/{id}` → 204 (np. stara wersja ustawy)

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

## POST /anonimizacja
Propozycje dla dowolnego tekstu, np. treści wniosku przed zapisem albo projektu pisma.
Body JSON: `{ "tekst": str, "wnioskodawca": str | null, "llm": bool = true }`.
Zwraca obiekt Propozycje. Błąd 422 oznacza błędne body.
