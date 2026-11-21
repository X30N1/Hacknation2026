## POST /llm/request

Czego się spodziewa:
 - id rozmowy: int (zwraca nową liczbę w razie gdy podane zostanie -1)
 - Prompt: str (Prośba bazowa użytkownika)
 - Kontekst arr[string] (PRZETWARZANIE OCR NA UŻYTKOWNIKU LOKALNYM)

 Co zwraca:
 - thread_id: int (id wątku wiadomości)
 - message_id: int (numer wiadomośći w rozmowie / wątku)
 - content: str (odpowiedź od LLM)
 - timestamp (GG-MM:DD-MM-RRRR)
 - sources: ARRAY (fragmenty wcześniejszych rozmów użyte przez RAG, może być puste)
   - thread_id: int
   - message_id: int
   - title: str (tytuł wątku źródłowego)
   - snippet: str (fragment tekstu)
   - score: float (trafność)

## GET /llm/all

Co oczekuje:
nic
Co zwraca:
ARRAY
- id: int (index)
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

czego oczekuje:
ID wątku
Co oddaje
ARR
- id: (id wiadomości)
- content: str (odpowiedzi LLM)
- timestamp: str (GG-MM:DD-MM-RRRR)

## GET /calendar

Czego się spodziewa:
- nic: zwraca listę wszystkich wydarzeń
BĄDŹ
dane do filtrowania kwerendy


Co oddaje:
LISTA
- id: int
- name: str
- add_date: str (DD-MM-RRRR)
- due_date: str (DD-MM-RRRR)
- response_date: str (DD-MM-RRRR) | null - (Data oddania odpowiedzi)
- status: bool (czy odpowiedź wysłana czy nie)
- initials: str (example. "ŁW")
- petition_id: int
- short_desc: str (TODO: limit)
- intake_date: str (DD-MM-RRRR)

## POST /calendar

Dodaje to co GET zwraca
