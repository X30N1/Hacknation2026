// Klient API zgodny z backend/docs/APIDOC.md (w dev: proxy Vite /api → localhost:8000).
import { ApiError } from './errors'

function qs(params = {}) {
  const p = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  return p.length ? '?' + new URLSearchParams(p).toString() : ''
}

async function http(method, path, body, signal) {
  const opts = { method, headers: {}, signal }
  if (body instanceof FormData) opts.body = body
  else if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }

  let res
  try {
    res = await fetch('/api' + path, opts)
  } catch (e) {
    if (e?.name === 'AbortError') throw e // anulowane przez użytkownika (AbortController)
    throw new ApiError('Brak połączenia z serwerem aplikacji. Sprawdź, czy backend jest uruchomiony.', 0)
  }
  // Sesja wygasła / wylogowano na innym urządzeniu -> App pokazuje ekran logowania.
  if (res.status === 401 && !path.startsWith('/auth/')) window.dispatchEvent(new Event('sesja-wygasla'))
  if (!res.ok) {
    let msg = `Błąd serwera (${res.status})`
    try {
      const j = await res.json()
      // FastAPI: {"detail": "tekst"} albo przy walidacji (422) {"detail": [{"loc": [...], "msg": "..."}]}
      const detail = Array.isArray(j.detail)
        ? j.detail.map((d) => `${(d.loc || []).slice(1).join('.')}: ${d.msg}`).join('; ')
        : j.detail
      msg = j.blad || detail || msg
    } catch {
      /* odpowiedź bez JSON */
    }
    throw new ApiError(msg, res.status)
  }
  if (res.status === 204) return null
  const ct = res.headers.get('content-type') || ''
  return ct.includes('application/json') ? res.json() : res.blob()
}

function form(fields) {
  const f = new FormData()
  for (const [k, v] of Object.entries(fields)) if (v !== undefined && v !== null) f.append(k, v)
  return f
}

export const api = {
  health: () => http('GET', '/health'),

  // logowanie: hasło -> (drugi składnik) -> (zmiana hasła) -> (konfiguracja 2FA) -> OK
  ja: () => http('GET', '/auth/ja'),
  zaloguj: (login, haslo) => http('POST', '/auth/login', { login, haslo }),
  wyloguj: () => http('POST', '/auth/wyloguj'),
  zmienHaslo: (stare, nowe) => http('POST', '/auth/haslo', { stare, nowe }),
  totpNowy: () => http('POST', '/auth/totp/nowy'),
  totpPotwierdz: (kod) => http('POST', '/auth/totp/potwierdz', { kod }),
  totpWeryfikuj: (kod) => http('POST', '/auth/totp/weryfikuj', { kod }),
  totpWylacz: () => http('DELETE', '/auth/totp'),
  kluczRejestracjaOpcje: () => http('POST', '/auth/klucz/rejestracja/opcje'),
  kluczRejestracja: (credential, nazwa) => http('POST', '/auth/klucz/rejestracja', { credential, nazwa }),
  kluczLogowanieOpcje: () => http('POST', '/auth/klucz/logowanie/opcje'),
  kluczLogowanie: (credential) => http('POST', '/auth/klucz/logowanie', { credential }),
  klucze: () => http('GET', '/auth/klucze'),
  usunKlucz: (id) => http('DELETE', `/auth/klucze/${id}`),

  // administrator
  uzytkownicy: () => http('GET', '/uzytkownicy'),
  dodajUzytkownika: (dane) => http('POST', '/uzytkownicy', dane),
  usunUzytkownika: (id) => http('DELETE', `/uzytkownicy/${id}`),
  ustawHaslo: (id, haslo) => http('POST', `/uzytkownicy/${id}/haslo`, { haslo }),
  resetuj2fa: (id) => http('POST', `/uzytkownicy/${id}/reset-2fa`),
  bezpieczenstwo: () => http('GET', '/ustawienia/bezpieczenstwo'),
  zapiszBezpieczenstwo: (dane) => http('PUT', '/ustawienia/bezpieczenstwo', dane),

  sprawy: (filtry) => http('GET', '/sprawy' + qs(filtry)),
  sprawa: (id) => http('GET', `/sprawy/${id}`),
  // Odczyt tekstu BEZ zapisu – oryginał trafia na serwer tylko na czas OCR; do bazy idzie wersja zanonimizowana.
  odczytajWniosek: (plik) => http('POST', '/wnioski/odczyt', form({ plik })),
  odczytajDokument: (plik) => http('POST', '/dokumenty/odczyt', form({ plik })),
  utworzSprawe: (dane) => http('POST', '/sprawy', dane),
  dodajZdarzenie: (id, dane) => http('POST', `/sprawy/${id}/zdarzenia`, dane),
  dodajDokument: (id, plik, rodzaj, wydzial) =>
    http('POST', `/sprawy/${id}/dokumenty`, form({ plik, rodzaj, wydzial })),
  poprawTekst: (dokumentId, tekst) => http('PATCH', `/dokumenty/${dokumentId}`, { tekst }),
  anonimizacjaTekstu: (tekst, wnioskodawca) => http('POST', '/anonimizacja', { tekst, wnioskodawca }),
  pobierzDocx: (dokumentId) => http('GET', `/dokumenty/${dokumentId}/docx`),

  // archiwum, ścieżka (wydziały), projekt odpowiedzi
  podobneSprawy: (id) => http('GET', `/sprawy/${id}/podobne`),
  sugestieWydzialow: (id) => http('GET', `/sprawy/${id}/wydzialy`),
  projektOdpowiedzi: (id) => http('POST', `/sprawy/${id}/projekt`),
  // projekt pisma: { rodzaj: ODPOWIEDZ | WEZWANIE | PRZEKAZANIE | PRZEDLUZENIE, wydzialy?, nowy_termin? }
  draftPisma: (id, dane, signal) => http('POST', `/sprawy/${id}/draft`, dane, signal),
  szukajWArchiwum: (q) => http('GET', '/archiwum/szukaj' + qs({ q })),

  // baza wiedzy: ustawy, zarządzenia, wzory pism, archiwalne pisma
  wiedza: () => http('GET', '/wiedza'),
  dodajWiedze: (plik, rodzaj) => http('POST', '/wiedza', form({ plik, rodzaj })),
  czytajWiedze: (id) => http('GET', `/wiedza/${id}`),
  usunWiedze: (id) => http('DELETE', `/wiedza/${id}`),
}
