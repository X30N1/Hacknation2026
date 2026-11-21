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

## GET /llm/all

Co oczekuje:
nic
Co zwraca:
ARRAY
- id: int (index)
- title: str (auto generowana nazwa wątku)
- create_date: str (GG-MM:DD-MM-RRRR, data pierwszej wiadomości wątku)

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
