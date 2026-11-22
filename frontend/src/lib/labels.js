// Statusy wg opisu wyzwania (a–e) + doprecyzowanie i pozostawienie bez rozpoznania.
export const STATUS = {
  NOWY: { label: 'Brak działań', kod: 'a' },
  W_WYDZIALACH: { label: 'Zapytania w wydziałach', kod: 'b' },
  DOPRECYZOWANIE: { label: 'Wezwanie do doprecyzowania', kod: '' },
  PRZEDLUZONA: { label: 'Kwerenda (przedłużenie)', kod: 'c' },
  PROJEKT_GOTOWY: { label: 'Odpowiedź przygotowana', kod: 'd' },
  WYSLANA: { label: 'Odpowiedź wysłana', kod: 'e' },
  BEZ_ROZPOZNANIA: { label: 'Bez rozpoznania', kod: '' },
  ZAMKNIETA: { label: 'Zamknięta (administrator)', kod: '' },
}

export const PILNOSC = {
  PRZEKROCZONY: { label: 'Po terminie', opis: 'termin minął' },
  DZIS: { label: 'Dziś', opis: 'termin upływa dziś' },
  JUTRO: { label: 'Jutro', opis: 'termin upływa jutro' },
  WKROTCE: { label: '≤ 3 dni', opis: 'termin w ciągu 3 dni' },
  BRAK: { label: '', opis: 'w terminie' },
  ZAMKNIETA: { label: '', opis: 'sprawa zamknięta' },
}

export const ZDARZENIE = {
  REJESTRACJA: 'Rejestracja wniosku',
  PRZEKAZANIE: 'Przekazano do wydziałów',
  ODP_WYDZIALU: 'Odpowiedź wydziału',
  WEZWANIE_DOPRECYZOWANIE: 'Wezwanie do doprecyzowania',
  DOPRECYZOWANIE_OTRZYMANE: 'Otrzymano doprecyzowanie',
  PRZEDLUZENIE: 'Przedłużenie terminu (kwerenda)',
  PROJEKT: 'Projekt odpowiedzi gotowy',
  WYSLANO: 'Odpowiedź wysłana',
  BEZ_ROZPOZNANIA: 'Pozostawiono bez rozpoznania',
  ZAMKNIECIE: 'Sprawa zamknięta przez administratora',
  WZNOWIENIE: 'Sprawa wznowiona przez administratora',
  DOKUMENT_DODANIE: 'Dodano dokument',
  DOKUMENT_ZMIANA: 'Zmieniono dokument',
  DOKUMENT_USUNIECIE: 'Usunięto dokument',
  SPRAWA_ZMIANA: 'Zmieniono dane wniosku',
}

export const RODZAJ_DOKUMENTU = {
  WNIOSEK: 'Wniosek',
  ODP_WYDZIALU: 'Odpowiedź wydziału',
  PROJEKT: 'Projekt odpowiedzi',
  ODPOWIEDZ: 'Odpowiedź',
  KWERENDA: 'Kwerenda',
  WEZWANIE: 'Wezwanie do doprecyzowania',
  DOPRECYZOWANIE: 'Doprecyzowanie wniosku',
  ZAPYTANIE: 'Zapytanie do wydziału',
  INNE: 'Inny dokument',
  // baza wiedzy
  USTAWA: 'Ustawa / przepis',
  ZARZADZENIE: 'Zarządzenie / instrukcja',
  WZOR: 'Wzór pisma',
  ARCHIWUM: 'Archiwalne pismo',
  SPRAWA: 'Sprawa',
}

export const RODZAJE_W_SPRAWIE = ['ODP_WYDZIALU', 'WNIOSEK', 'DOPRECYZOWANIE', 'ZAPYTANIE', 'ODPOWIEDZ', 'KWERENDA', 'WEZWANIE', 'INNE']
export const RODZAJE_WIEDZY = ['USTAWA', 'ZARZADZENIE', 'WZOR', 'ARCHIWUM']

export const ZRODLO_SUGESTII = {
  ARCHIWUM: 'podobne sprawy',
  LLM: 'model AI',
  SLOWA_KLUCZOWE: 'słowa kluczowe',
}

export const METODA = {
  DOCX: 'Word',
  PDF_TEXT: 'PDF (warstwa tekstowa)',
  OCR: 'OCR (skan)',
  RECZNA: 'wpisany ręcznie',
}
