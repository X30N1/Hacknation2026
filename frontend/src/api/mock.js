// Mock backendu (tylko do pracy nad UI bez serwera). Logika terminów tu jest UPROSZCZONĄ kopią –
// źródłem prawdy jest backend (cases/rules). Stan w pamięci; odświeżenie strony go resetuje.
import { addDays, addMonths, diffDays, isWeekend, todayISO } from '../lib/dates'
import { ApiError } from './errors'
import { KATEGORIE, wykryj } from '../lib/anonimizacja'

const DZIS = todayISO()
const ROK = Number(DZIS.slice(0, 4))
const d = (n) => addDays(DZIS, n)

// --- 10 spraw z kalendarium xlsx (stan „jak zaimportowano”, z flagami z docs/ANALIZA.md §5) ---
const XLSX = [
  { znak: 'BKS.IV.1431.293.2025', wnioskodawca: 'Antoni Ptak Stowarzyszenie Obrony Zwierzątek', przedmiot: 'Opieka i odławianie bezdomnych zwierząt.', data_wplywu: '2025-06-12', termin: '2025-06-26', data_odpowiedzi: '2025-06-26', inicjaly: 'Pracownik 1',
    flagi: [{ kod: 'WNIOSKODAWCA_WARIANTY', opis: 'Ten sam wnioskodawca zapisany inaczej w sprawie 543.2026 („Stowarzyszenie Obrony Zwierzątek”).', propozycja: 'Ujednolicić nazwę wnioskodawcy.' }] },
  { znak: 'BKS.IV.1431.307.2025', wnioskodawca: 'Ewa Góra', przedmiot: 'Aktualne zestawienie liczby uczniów w szkołach podstawowych. Proszę też o podanie liczby obcokrajowców w poszczególnych szkołach.', data_wplywu: '2025-06-25', termin: '2025-07-09', data_odpowiedzi: '2025-07-08', inicjaly: 'Pracownik 2', flagi: [] },
  { znak: 'BKS.IV.1431.15.2026', wnioskodawca: 'Jacek Rzeźbiarz', przedmiot: 'Zapytanie o rzeźbę Ludmiły Stehnovej, która została usunięta z wyspy Ronda Grunwaldzkiego.', data_wplywu: '2026-09-12', termin: '2026-09-26', data_odpowiedzi: '2026-01-14', inicjaly: 'Pracownik 2',
    flagi: [
      { kod: 'ODP_PRZED_WPLYWEM', opis: 'Data odpowiedzi (14.01.2026) jest wcześniejsza niż data wpływu (12.09.2026).' },
      { kod: 'NUMERACJA_NIEZGODNA', opis: 'Sprawa nr 16.2026 wpłynęła 09.01.2026, więc nr 15 nie mógł wpłynąć we wrześniu.', propozycja: 'Prawdopodobna data wpływu: ok. 08.01.2026.' },
      { kod: 'TERMIN_W_WEEKEND', opis: 'Termin 26.09.2026 przypada w sobotę.' },
    ] },
  { znak: 'BKS.IV.1431.16.2026', wnioskodawca: 'Jerzy Dociekliwy', przedmiot: 'Pytanie o liczbę punktów sprzedaży alkoholu powstałych od objęcia funkcji prezydenta przez Rafała Bruskiego do dzisiaj.', data_wplywu: '2026-01-09', termin: '2026-01-23', data_odpowiedzi: '2026-01-20', inicjaly: 'Pracownik 1', flagi: [] },
  { znak: 'BKS.IV.1431.17.2026', wnioskodawca: 'abcxyz@jahu.komm', przedmiot: 'Udostępnienie informacji publicznej dot. realizacji umowy nr 102/TT/2019 z Jakotako spółką z o.o.', data_wplywu: '2026-01-14', termin: '2026-01-28', data_odpowiedzi: '2026-01-15', inicjaly: 'Pracownik 2',
    flagi: [{ kod: 'WNIOSKODAWCA_EMAIL', opis: 'Wnioskodawca zapisany jako adres e-mail (dana osobowa).' }] },
  { znak: 'BKS.IV.1431.18.2026', wnioskodawca: 'Ksiądz', przedmiot: 'Liczba mieszkańców wskazanych ulic według opłat za gospodarowanie odpadami komunalnymi.', data_wplywu: '2026-01-15', termin: '2025-01-29', data_odpowiedzi: '2026-01-26', inicjaly: 'Pracownik 1',
    flagi: [{ kod: 'ROK_TERMINU', opis: 'Termin 29.01.2025 ma rok wcześniejszy niż rok sprawy; wpływ 15.01.2026 + 14 dni = 29.01.2026.', propozycja: 'Termin: 29.01.2026.' }] },
  { znak: 'BKS.IV.1431.509.2026', wnioskodawca: 'Ewa Górna', przedmiot: 'Dokumentacja dotycząca basenu Astorii: projekt zagospodarowania terenu; projekt zagospodarowania zieleni; wizualizacje; zestawienie parametrów technicznych budynku.', data_wplywu: '2026-08-05', termin: '2026-09-18', data_odpowiedzi: '2026-09-14', inicjaly: 'Pracownik 2',
    flagi: [
      { kod: 'TERMIN_TEKSTOWY', opis: 'Termin w xlsx zapisany tekstem: „19.08.2026/18.09.2026 – doprecyzowanie wniosku”. Zapisano jako wezwanie do doprecyzowania z nowym terminem 18.09.2026.' },
      { kod: 'WNIOSKODAWCA_WARIANTY', opis: 'W xlsx „Ewa Górna”, a we wniosku podpis „E. Góra” (por. sprawy 307.2025 i 599.2026).' },
      { kod: 'PRZEDMIOT_NIEZGODNY', opis: 'Przedmiot w xlsx mówi o basenie Astorii, a wniosek dotyczy apartamentowca na terenie po budynku Astrum.' },
    ] },
  { znak: 'BKS.IV.1431.543.2026', wnioskodawca: 'Stowarzyszenie Obrony Zwierzątek', przedmiot: 'Opieka nad bezdomnymi zwierzętami i ich wyłapywanie.', data_wplywu: '2026-08-14', termin: '2026-08-28', data_odpowiedzi: '2026-09-22', inicjaly: 'Pracownik 2',
    flagi: [
      { kod: 'ODP_PO_TERMINIE', opis: 'Odpowiedź 22.09.2026 po terminie 28.08.2026, a w xlsx nie ma przedłużenia. W archiwum jest pismo „Kwerenda” z terminem 25.09.', propozycja: 'Dodać zdarzenie przedłużenia do 25.09.2026.' },
      { kod: 'ZNAK_W_TRESCI_INNY', opis: 'Pisma kwerendy i odpowiedzi mają w treści znak BKS.IV.1431.543.2025.' },
      { kod: 'DATA_WPLYWU_PIECZEC', opis: 'Pieczęć wpływu na wniosku: 19.08.2026 (xlsx: 14.08.2026).' },
    ] },
  { znak: 'BKS.IV.1431.590.2026', wnioskodawca: 'Budowlanka S.A.', przedmiot: 'Kompleks Astoria.', data_wplywu: '2026-09-07', termin: '2026-09-21', data_odpowiedzi: '2026-09-29', inicjaly: 'Pracownik 2',
    flagi: [
      { kod: 'ODP_PO_TERMINIE', opis: 'Odpowiedź po terminie 21.09.2026, brak przedłużenia.' },
      { kod: 'DATA_PISMA_INNA', opis: 'Pismo odpowiedzi datowane 25.09.2026, a w xlsx 29.09.2026.' },
    ] },
  { znak: 'BKS.IV.1431.599.2026', wnioskodawca: 'Ewa Góra', przedmiot: 'Edytowalne zestawienie liczby uczniów oraz uczniów cudzoziemców w poszczególnych szkołach podstawowych w Bydgoszczy – stan na koniec czerwca 2026 oraz stan na wrzesień 2026.', data_wplywu: '2026-09-08', termin: '2026-09-22', data_odpowiedzi: '2026-09-18', inicjaly: 'Pracownik 2', flagi: [] },
]

// --- 10 spraw demo z datami względem dziś (docs/TESTY.md J5.b); status liczony ze zdarzeń ---
const DEMO = [
  { nr: 701, wnioskodawca: 'Fundacja Przejrzysta Gmina', przedmiot: 'Wykaz dotacji dla organizacji pozarządowych w bieżącym roku.', wplyw: -30, inicjaly: 'AK',
    zdarzenia: [['PRZEKAZANIE', -29, { wydzialy: ['BAS'] }], ['PROJEKT', -20], ['WYSLANO', -18]] },
  { nr: 702, wnioskodawca: 'Redakcja „Gazeta Testowa”', przedmiot: 'Koszty utrzymania zieleni miejskiej w latach 2020–2026.', wplyw: -20, inicjaly: 'MN',
    zdarzenia: [['PRZEKAZANIE', -19, { wydzialy: ['WGK'] }], ['PRZEDLUZENIE', -7, { powod: 'kwerenda w archiwum' }, 10]] },
  { nr: 703, wnioskodawca: 'Jan Testowy', przedmiot: 'Liczba wydanych pozwoleń na budowę w bieżącym roku.', wplyw: -15, inicjaly: 'AK',
    zdarzenia: [['PRZEKAZANIE', -14, { wydzialy: ['WAB'] }]] },
  { nr: 704, wnioskodawca: 'Stowarzyszenie Miasto Dla Ludzi', przedmiot: 'Umowy na zimowe utrzymanie ulic.', wplyw: -14, inicjaly: 'MN',
    zdarzenia: [['PRZEKAZANIE', -13, { wydzialy: ['WGK'] }]] },
  { nr: 705, wnioskodawca: 'Anna Przykładowa', przedmiot: 'Koszt organizacji Dni Bydgoszczy.', wplyw: -14, inicjaly: 'AK',
    zdarzenia: [['PRZEKAZANIE', -13, { wydzialy: ['BKB'] }], ['ODP_WYDZIALU', -3, { wydzial: 'BKB' }], ['PROJEKT', -1]] },
  { nr: 706, wnioskodawca: 'Piotr Fikcyjny', przedmiot: 'Liczba miejsc w żłobkach miejskich.', wplyw: -13, inicjaly: null, zdarzenia: [] },
  { nr: 707, wnioskodawca: 'Redakcja Portalu Demo', przedmiot: 'Wydatki na promocję miasta w mediach społecznościowych.', wplyw: -11, inicjaly: 'MN',
    zdarzenia: [['PRZEKAZANIE', -10, { wydzialy: ['BP'] }], ['PROJEKT', -2]] },
  { nr: 708, wnioskodawca: 'Maria Wzorcowa', przedmiot: 'Dokumentacja inwestycji przy ul. Przykładowej.', wplyw: -10, inicjaly: 'AK',
    zdarzenia: [['WEZWANIE_DOPRECYZOWANIE', -8, { dni_na_doprecyzowanie: 7 }]] },
  { nr: 709, wnioskodawca: 'Tomasz Demo', przedmiot: 'Lista pustostanów w zasobie gminy.', wplyw: -5, inicjaly: 'MN',
    zdarzenia: [['PRZEKAZANIE', -4, { wydzialy: ['WMG'] }]] },
  { nr: 710, wnioskodawca: 'Rada Rodziców SP nr 99', przedmiot: 'Harmonogram remontów szkół w przyszłym roku.', wplyw: -1, inicjaly: null, zdarzenia: [] },
]

let nextId = 1
let nextEvId = 1
let nextDocId = 1
const sprawy = []
const dokumenty = []

// Odpowiedź jak z backendu (POST /anonimizacja), ale tylko z lokalnych wzorców.
const propozycje = (tekst) => ({
  fragmenty: wykryj(tekst).map((f) => ({ ...f, etykieta: KATEGORIE[f.kategoria], zrodlo: 'WZORZEC', powod: null })),
  llm_uzyty: false,
  uwagi: ['Mock: propozycje tylko z wzorców.'],
})

function ev(typ, data, payload = {}, nowy_termin = null, inicjaly = null) {
  return { id: nextEvId++, typ, data, nowy_termin, payload, inicjaly }
}

for (const x of XLSX) {
  const [, , , nr, rok] = x.znak.split('.')
  const zdarzenia = [ev('REJESTRACJA', x.data_wplywu)]
  if (x.znak.endsWith('509.2026')) zdarzenia.push(ev('WEZWANIE_DOPRECYZOWANIE', '2026-08-10', { dni_na_doprecyzowanie: 7 }, '2026-09-18'))
  zdarzenia.push(ev('WYSLANO', x.data_odpowiedzi))
  sprawy.push({ id: nextId++, nr: Number(nr), rok: Number(rok), zrodlo: 'import', zdarzenia, xlsx: x, ...x })
}

for (const s of DEMO) {
  const data_wplywu = d(s.wplyw)
  const zdarzenia = [ev('REJESTRACJA', data_wplywu)]
  for (const [typ, off, payload, termOff] of s.zdarzenia) {
    // 4. element krotki = nowy termin jako przesunięcie od dziś (np. przedłużenie do D+10)
    zdarzenia.push(ev(typ, d(off), payload || {}, termOff !== undefined ? d(termOff) : null))
  }
  sprawy.push({
    id: nextId++, znak: `BKS.IV.1431.${s.nr}.${ROK}`, nr: s.nr, rok: ROK, zrodlo: 'demo',
    wnioskodawca: s.wnioskodawca, przedmiot: s.przedmiot, data_wplywu, inicjaly: s.inicjaly, flagi: [], zdarzenia,
  })
}

// Uproszczone przeliczenie statusu i terminu (kopia reguł z docs/ANALIZA.md §4 – backend jest źródłem prawdy).
function przelicz(s) {
  const out = { ...s }
  delete out.xlsx

  if (s.xlsx) {
    // sprawy z importu: pokazujemy wartości z xlsx „jak są”, flagi opisują problemy
    return { ...out, termin_wstrzymany: false, status: 'WYSLANA', pilnosc: 'ZAMKNIETA', pozostalo_dni: null, przedluzenie_dni: null }
  }

  let termin = addDays(s.data_wplywu, 14)
  let status = 'NOWY'
  let wstrzymany = false
  let przedluzenie = null
  let odp = null
  let wezwanieData = null
  const flagi = [...(s.flagi || [])]

  for (const e of [...s.zdarzenia].sort((a, b) => a.data.localeCompare(b.data) || a.id - b.id)) {
    switch (e.typ) {
      case 'PRZEKAZANIE':
        if (status === 'NOWY') status = 'W_WYDZIALACH'
        break
      case 'WEZWANIE_DOPRECYZOWANIE':
        status = 'DOPRECYZOWANIE'
        wezwanieData = e.data
        if (e.nowy_termin) termin = e.nowy_termin
        else wstrzymany = true
        break
      case 'DOPRECYZOWANIE_OTRZYMANE':
        status = 'W_WYDZIALACH'
        wstrzymany = false
        termin = addDays(e.data, 14)
        break
      case 'PRZEDLUZENIE':
        przedluzenie = diffDays(e.nowy_termin, termin)
        termin = e.nowy_termin
        status = 'PRZEDLUZONA'
        break
      case 'PROJEKT':
        status = 'PROJEKT_GOTOWY'
        break
      case 'WYSLANO':
        status = 'WYSLANA'
        odp = e.data
        break
      case 'BEZ_ROZPOZNANIA':
        status = 'BEZ_ROZPOZNANIA'
        odp = e.data
        break
    }
  }

  const zamknieta = status === 'WYSLANA' || status === 'BEZ_ROZPOZNANIA'
  let pilnosc = 'ZAMKNIETA'
  let pozostalo = null
  if (!zamknieta && wstrzymany) pilnosc = 'BRAK'
  else if (!zamknieta) {
    pozostalo = diffDays(termin, DZIS)
    pilnosc = pozostalo < 0 ? 'PRZEKROCZONY' : pozostalo === 0 ? 'DZIS' : pozostalo === 1 ? 'JUTRO' : pozostalo <= 3 ? 'WKROTCE' : 'BRAK'
    if (isWeekend(termin)) flagi.push({ kod: 'TERMIN_W_WEEKEND', opis: 'Termin przypada w weekend – sprawdź zasadę liczenia (art. 57 § 4 KPA).' })
  }
  if (status === 'DOPRECYZOWANIE' && wezwanieData && diffDays(DZIS, addDays(wezwanieData, 7)) > 0) {
    flagi.push({ kod: 'DOPRECYZOWANIE_MINELO', opis: 'Minęło 7 dni na doprecyzowanie.', propozycja: 'Rozważ pozostawienie wniosku bez rozpoznania.' })
  }
  if (diffDays(termin, s.data_wplywu) > 14 && diffDays(termin, addMonths(s.data_wplywu, 2)) > 0) {
    flagi.push({ kod: 'PRZEDLUZENIE_PONAD_2_MIES', opis: 'Nowy termin przekracza 2 miesiące od dnia wpływu (art. 13 ust. 2 UDIP).' })
  }

  return {
    ...out, termin: wstrzymany ? null : termin, termin_wstrzymany: wstrzymany, status, pilnosc,
    pozostalo_dni: pozostalo, przedluzenie_dni: przedluzenie, data_odpowiedzi: odp, flagi,
  }
}

function lista(params) {
  let wynik = sprawy.map(przelicz)
  if (params.get('rok')) wynik = wynik.filter((s) => String(s.rok) === params.get('rok'))
  if (params.get('otwarte') === '1') wynik = wynik.filter((s) => s.pilnosc !== 'ZAMKNIETA')
  return wynik
    .sort((a, b) => a.data_wplywu.localeCompare(b.data_wplywu) || a.nr - b.nr)
    .map(({ zdarzenia, ...rest }) => rest) // eslint-disable-line no-unused-vars
}

function szczegoly(id) {
  const s = sprawy.find((x) => x.id === id)
  if (!s) throw blad(404, 'Nie znaleziono sprawy.')
  return { ...przelicz(s), dokumenty: dokumenty.filter((x) => x.sprawa_id === id) }
}

function blad(status, msg) {
  const e = new Error(msg)
  e.status = status
  return e
}

const wait = (ms) => new Promise((r) => setTimeout(r, ms))
const clone = (x) => JSON.parse(JSON.stringify(x))

async function analiza(formData) {
  const plik = formData.get('plik')
  const nazwa = plik?.name || 'plik'
  const ext = nazwa.split('.').pop().toLowerCase()
  if (!['pdf', 'docx', 'txt'].includes(ext)) throw blad(415, 'Nieobsługiwany format. Wgraj plik PDF lub Word (DOCX).')
  const znak = nazwa.match(/BKS\.IV\.1431\.\d+\.\d{4}/)?.[0]
  const tekst = ext === 'txt'
    ? await plik.text()
    : `(Tryb demonstracyjny bez backendu.)\nTreść pliku „${nazwa}” zostanie odczytana przez serwer. Tu możesz wpisać lub poprawić tekst wniosku ręcznie.`
  const doc = {
    id: nextDocId++, sprawa_id: null, rodzaj: 'WNIOSEK', nazwa_pliku: nazwa, wydzial: null,
    metoda: ext === 'pdf' ? 'OCR' : ext === 'docx' ? 'DOCX' : 'RECZNA', ocr_pewnosc: ext === 'pdf' ? 0.42 : null,
    tekst, url_podgladu: '',
  }
  dokumenty.push(doc)
  const maxNr = Math.max(...sprawy.filter((s) => s.rok === ROK).map((s) => s.nr), 0)
  return {
    dokument: doc,
    propozycja: { znak: znak || `BKS.IV.1431.${maxNr + 1}.${ROK}`, data_wplywu: DZIS, wnioskodawca: '', przedmiot: tekst.split('\n')[0].slice(0, 160) },
  }
}

function utworz(body) {
  if (!/^BKS\.IV\.1431\.\d+\.\d{4}$/.test(body.znak || '')) throw blad(422, 'Numer sprawy musi mieć format BKS.IV.1431.<nr>.<rok>.')
  if (sprawy.some((s) => s.znak === body.znak)) throw blad(409, `Sprawa ${body.znak} już istnieje.`)
  const [, , , nr, rok] = body.znak.split('.')
  const s = {
    id: nextId++, znak: body.znak, nr: Number(nr), rok: Number(rok), zrodlo: 'upload',
    wnioskodawca: body.wnioskodawca || '', przedmiot: body.przedmiot || '', data_wplywu: body.data_wplywu,
    inicjaly: body.inicjaly || null, flagi: [], zdarzenia: [ev('REJESTRACJA', body.data_wplywu, {}, null, body.inicjaly)],
  }
  sprawy.push(s)
  const doc = dokumenty.find((x) => x.id === body.dokument_id)
  if (doc) doc.sprawa_id = s.id
  return przelicz(s)
}

export async function handle(method, path, body) {
  await wait(150)
  const [p, q] = path.split('?')
  const params = new URLSearchParams(q || '')
  let m
  try {
    if (method === 'GET' && p === '/health')
      return { ok: true, dzis: DZIS, llm: { backend: 'mock', model: '—', dostepny: false, zewnetrzny: false } }
    if (method === 'GET' && p === '/sprawy') return clone(lista(params))
    if (method === 'GET' && (m = p.match(/^\/sprawy\/(\d+)$/))) return clone(szczegoly(Number(m[1])))
    if (method === 'POST' && p === '/wnioski/analiza') return clone(await analiza(body))
    if (method === 'POST' && p === '/sprawy') return clone(utworz(body))
    if (method === 'PATCH' && (m = p.match(/^\/sprawy\/(\d+)$/))) {
      const s = sprawy.find((x) => x.id === Number(m[1]))
      Object.assign(s, body)
      return clone(przelicz(s))
    }
    if (method === 'POST' && (m = p.match(/^\/sprawy\/(\d+)\/zdarzenia$/))) {
      const s = sprawy.find((x) => x.id === Number(m[1]))
      if (s.xlsx) throw blad(409, 'Sprawa z importu archiwalnego jest zamknięta.')
      s.zdarzenia.push(ev(body.typ, body.data, body.payload || {}, body.nowy_termin || null, body.inicjaly || null))
      return clone(przelicz(s))
    }
    if (method === 'POST' && (m = p.match(/^\/sprawy\/(\d+)\/dokumenty$/))) {
      const s = sprawy.find((x) => x.id === Number(m[1]))
      const { dokument } = await analiza(body)
      Object.assign(dokument, { sprawa_id: s.id, rodzaj: body.get('rodzaj') || 'INNE' })
      return clone(dokument)
    }
    if (method === 'GET' && (m = p.match(/^\/dokumenty\/(\d+)\/anonimizacja$/))) {
      const doc = dokumenty.find((x) => x.id === Number(m[1]))
      if (!doc) throw blad(404, 'Nie znaleziono dokumentu.')
      return propozycje(doc.tekst)
    }
    if (method === 'POST' && p === '/anonimizacja') return propozycje(body.tekst)
    if (method === 'PATCH' && (m = p.match(/^\/dokumenty\/(\d+)$/))) {
      const doc = dokumenty.find((x) => x.id === Number(m[1]))
      doc.tekst = body.tekst
      return clone(doc)
    }
  } catch (e) {
    throw new ApiError(e.message, e.status || 500)
  }
  throw new ApiError(`Mock: brak obsługi ${method} ${p}`, 501)
}
