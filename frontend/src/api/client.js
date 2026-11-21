// Klient API zgodny z docs/API.md. Przy VITE_API_MOCK=1 zapytania obsługuje src/api/mock.js.
import { ApiError } from './errors'
import { handle as mockHandle } from './mock'

export { ApiError }
export const USE_MOCK = import.meta.env.VITE_API_MOCK === '1'

function qs(params = {}) {
  const p = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  return p.length ? '?' + new URLSearchParams(p).toString() : ''
}

async function http(method, path, body) {
  if (USE_MOCK) return mockHandle(method, path, body)

  const opts = { method, headers: {} }
  if (body instanceof FormData) opts.body = body
  else if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }

  let res
  try {
    res = await fetch('/api' + path, opts)
  } catch {
    throw new ApiError('Brak połączenia z serwerem aplikacji. Sprawdź, czy backend jest uruchomiony.', 0)
  }
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

  sprawy: (filtry) => http('GET', '/sprawy' + qs(filtry)),
  sprawa: (id) => http('GET', `/sprawy/${id}`),
  analizujWniosek: (plik) => http('POST', '/wnioski/analiza', form({ plik })),
  // Odczyt tekstu BEZ zapisu – oryginał trafia na serwer tylko na czas OCR; do bazy idzie wersja zanonimizowana.
  odczytajWniosek: (plik) => http('POST', '/wnioski/odczyt', form({ plik })),
  odczytajDokument: (plik) => http('POST', '/dokumenty/odczyt', form({ plik })),
  utworzSprawe: (dane) => http('POST', '/sprawy', dane),
  edytujSprawe: (id, dane) => http('PATCH', `/sprawy/${id}`, dane),
  dodajZdarzenie: (id, dane) => http('POST', `/sprawy/${id}/zdarzenia`, dane),
  dodajDokument: (id, plik, rodzaj, wydzial) =>
    http('POST', `/sprawy/${id}/dokumenty`, form({ plik, rodzaj, wydzial })),
  poprawTekst: (dokumentId, tekst) => http('PATCH', `/dokumenty/${dokumentId}`, { tekst }),
  anonimizacjaDokumentu: (dokumentId) => http('GET', `/dokumenty/${dokumentId}/anonimizacja`),
  anonimizacjaTekstu: (tekst, wnioskodawca) => http('POST', '/anonimizacja', { tekst, wnioskodawca }),
}
