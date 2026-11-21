// Wykrywanie danych do zamazania (lista „Dane podlegające anonimizacji”) – tylko PROPOZYCJE,
// o zamazaniu decyduje urzędnik. Wzorce działają lokalnie w przeglądarce.
// Nie wykryje imion i nazwisk bez kontekstu ani danych wrażliwych (zdrowie itp.) – te urzędnik zaznacza ręcznie.

export const KATEGORIE = {
  IMIE_NAZWISKO: 'Imię i nazwisko',
  PESEL: 'PESEL',
  NIP: 'NIP',
  DOWOD: 'Dokument tożsamości',
  DATA_URODZENIA: 'Data urodzenia',
  ADRES: 'Adres',
  TELEFON: 'Telefon',
  EMAIL: 'E-mail',
  KONTO: 'Rachunek bankowy',
  POJAZD: 'Numer rejestracyjny pojazdu',
  KSIEGA_WIECZYSTA: 'Księga wieczysta',
  RECZNIE: 'Zaznaczone ręcznie',
}

export const ZASLONA = '█████' // stała długość – długość zamazanego tekstu nie może go zdradzać

const DUZA = 'A-ZĄĆĘŁŃÓŚŹŻ'
const MALA = 'a-ząćęłńóśźż'

function peselOk(s) {
  if (!/^\d{11}$/.test(s)) return false
  const w = [1, 3, 7, 9, 1, 3, 7, 9, 1, 3]
  const suma = w.reduce((a, k, i) => a + k * Number(s[i]), 0)
  return (10 - (suma % 10)) % 10 === Number(s[10])
}

function nipOk(s) {
  const c = s.replace(/\D/g, '')
  if (c.length !== 10) return false
  const w = [6, 5, 7, 2, 3, 4, 5, 6, 7]
  const suma = w.reduce((a, k, i) => a + k * Number(c[i]), 0) % 11
  return suma !== 10 && suma === Number(c[9])
}

// [kategoria, wzorzec, numer grupy z zakresem (0 = całe dopasowanie), walidator]
const WZORCE = [
  ['EMAIL', /[\w.+-]+@[\w-]+(?:\.[\w-]+)+/g, 0],
  ['KONTO', /(?<!\d)(?:PL ?)?\d{2}(?: ?\d{4}){6}(?!\d)/g, 0],
  ['PESEL', /(?<!\d)\d{11}(?!\d)/g, 0, peselOk],
  ['NIP', /(?<!\d)\d{3}[- ]?\d{3}[- ]?\d{2}[- ]?\d{2}(?!\d)/g, 0, nipOk],
  ['DOWOD', /(?<![A-Z\d])[A-Z]{3} ?\d{6}(?!\d)/g, 0],
  ['KSIEGA_WIECZYSTA', /\b[A-Z]{2}\d[A-Z]\/\d{8}\/\d\b/g, 0],
  ['DATA_URODZENIA', /ur(?:\.|odzon\w*)\s*(?:dnia\s*)?(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4})/gi, 1],
  ['POJAZD', /rejestracyjn\w*\s*(?:nr|numer)?\s*:?\s*([A-Z]{1,3} ?\d[0-9A-Z]{3,5})\b/gi, 1],
  ['TELEFON', /(?<!\d)(?:\+48[ -]?)?\d{3}[ -]?\d{3}[ -]?\d{3}(?!\d)/g, 0],
  ['ADRES', new RegExp(
    `\\b(?:ul\\.|ulica|al\\.|aleja|os\\.|osiedle|pl\\.|plac)\\s+[${DUZA}\\d][\\w.\\- ]{1,40}?\\s\\d+[A-Za-z]?(?:\\s?/\\s?\\d+[A-Za-z]?)?`, 'g'), 0],
  ['ADRES', new RegExp(`\\b\\d{2}-\\d{3}\\s+[${DUZA}][${MALA}]+(?:[ -][${DUZA}][${MALA}]+)?`, 'g'), 0],
  ['IMIE_NAZWISKO', new RegExp(
    `\\b(?:Pan|Pani|Państwo|Panem|Panią|[Ii]mi[ęe] i nazwisko|[Ww]nioskodawc\\w+)\\b[:\\s]+((?:[${DUZA}][${MALA}]+(?:-[${DUZA}][${MALA}]+)?[ ]?){2,3})`, 'g'), 1],
]

// Zwraca [{ start, end, kategoria, tekst }] bez nakładających się zakresów, rosnąco po start.
export function wykryj(tekst) {
  const znalezione = []
  for (const [kategoria, wzor, grupa, ok] of WZORCE) {
    for (const m of tekst.matchAll(wzor)) {
      const fr = (m[grupa] ?? '').trimEnd()
      if (!fr || (ok && !ok(fr))) continue
      // indeks grupy: dopasowanie całe lub podciąg wewnątrz dopasowania
      const start = m.index + (grupa === 0 ? 0 : m[0].indexOf(m[grupa]))
      znalezione.push({ start, end: start + fr.length, kategoria, tekst: fr })
    }
  }
  znalezione.sort((a, b) => a.start - b.start || b.end - a.end)
  const wynik = []
  for (const f of znalezione) {
    if (wynik.length && f.start < wynik[wynik.length - 1].end) continue
    wynik.push(f)
  }
  return wynik
}

// Zastępuje zakresy stałą zasłoną; nakładające się łączy.
export function zamaz(tekst, zakresy) {
  const posortowane = zakresy.filter((z) => z.end > z.start).map((z) => [z.start, z.end]).sort((a, b) => a[0] - b[0])
  const scalone = []
  for (const [s, e] of posortowane) {
    const ost = scalone[scalone.length - 1]
    if (ost && s <= ost[1]) ost[1] = Math.max(ost[1], e)
    else scalone.push([s, e])
  }
  let wynik = ''
  let poz = 0
  for (const [s, e] of scalone) {
    wynik += tekst.slice(poz, s) + ZASLONA
    poz = e
  }
  return wynik + tekst.slice(poz)
}
