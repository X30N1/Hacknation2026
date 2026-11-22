import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { Flagi, PilnoscBadge, StatusBadge } from '../components/Badges'
import NowyDokument from '../components/NowyDokument'
import OcrBaner from '../components/OcrBaner'
import ProjektPisma from '../components/ProjektPisma'
import { jakoPlikTxt } from '../lib/anonimizacja'
import { addDays, addMonths, diffDays, formatPL, todayISO } from '../lib/dates'
import { METODA, RODZAJ_DOKUMENTU, RODZAJE_W_SPRAWIE, ZDARZENIE, ZRODLO_SUGESTII } from '../lib/labels'
import Podswietl from '../components/Podswietl'
import { bezRozszerzenia, pobierzBlob, pobierzTekst } from '../lib/pobierz'

const AKCEPTOWANE = '.pdf,.docx,.txt'
const ROBOCZE = ['W_WYDZIALACH', 'PRZEDLUZONA']

// Akcje w danym statusie (kolejność jak w przebiegu sprawy). `tryb`:
//   formularz – data/inicjały (+ wydziały / nowy termin), plik – wgranie dokumentu,
//   wybor – okno: A. prześlij plik / B. draft AI / tylko zapis w historii; po zapisaniu dokumentu
//           zdarzenie trafia do historii automatycznie.
// `dokument`: rodzaj zapisywanego dokumentu, `draft` – rodzaj pisma dla AI (brak = bez opcji B),
// `rodzajDraftu` – rodzaj dokumentu z draftu, gdy inny niż z pliku.
const AKCJE = [
  { id: 'przekazanie', typ: 'PRZEKAZANIE', label: 'Przekazano do wydziałów', tryb: 'wybor', pole: 'wydzialy', gdy: ['NOWY', ...ROBOCZE],
    dokument: { rodzaj: 'ZAPYTANIE', tytul: 'Zapytanie do wydziałów', draft: 'PRZEKAZANIE' } },
  { id: 'odp-wydzialu', typ: 'ODP_WYDZIALU', label: 'Odpowiedź wydziału – wgraj plik', tryb: 'plik', gdy: ROBOCZE },
  { id: 'odpowiedz', typ: 'PROJEKT', label: 'Odpowiedź na wniosek', tryb: 'wybor', glowna: true, gdy: ROBOCZE,
    dokument: { rodzaj: 'ODPOWIEDZ', rodzajDraftu: 'PROJEKT', tytul: 'Odpowiedź na wniosek', draft: 'ODPOWIEDZ' } },
  { id: 'wezwanie', typ: 'WEZWANIE_DOPRECYZOWANIE', label: 'Wezwanie do doprecyzowania', tryb: 'wybor', gdy: ['NOWY', 'W_WYDZIALACH'],
    dokument: { rodzaj: 'WEZWANIE', tytul: 'Wezwanie do doprecyzowania', draft: 'WEZWANIE' } },
  { id: 'doprecyzowanie', typ: 'DOPRECYZOWANIE_OTRZYMANE', label: 'Otrzymano doprecyzowanie', tryb: 'wybor', gdy: ['DOPRECYZOWANIE'],
    dokument: { rodzaj: 'DOPRECYZOWANIE', tytul: 'Doprecyzowanie wniosku' } },
  { id: 'przedluzenie', typ: 'PRZEDLUZENIE', label: 'Przedłuż termin (kwerenda)', tryb: 'wybor', pole: 'nowy_termin', gdy: ['NOWY', ...ROBOCZE],
    dokument: { rodzaj: 'KWERENDA', tytul: 'Zawiadomienie o przedłużeniu terminu', draft: 'PRZEDLUZENIE' } },
  { id: 'wyslano', typ: 'WYSLANO', label: 'Oznacz jako wysłaną', tryb: 'formularz', glowna: true, gdy: ['PROJEKT_GOTOWY'] },
  { id: 'bez', typ: 'BEZ_ROZPOZNANIA', label: 'Pozostaw bez rozpoznania', tryb: 'formularz', gdy: ['DOPRECYZOWANIE'] },
]
const AKCJA = Object.fromEntries(AKCJE.map((a) => [a.id, a]))

function FormularzAkcji({ akcja, sprawa, onZapisz, onAnuluj }) {
  const [data, setData] = useState(todayISO())
  const maxTermin = addMonths(sprawa.data_wplywu, 2)
  const proponowany = sprawa.termin ? addDays(sprawa.termin, 14) : ''
  const [nowyTermin, setNowyTermin] = useState(
    proponowany && diffDays(proponowany, maxTermin) > 0 ? maxTermin : proponowany)
  const [wydzialy, setWydzialy] = useState((akcja.wydzialy || []).join(', '))
  const [inicjaly, setInicjaly] = useState(sprawa.inicjaly || '')
  // Kalendarz (atrybut max) blokuje wybór, ale datę można jeszcze wpisać ręcznie – stąd też blokada zapisu.
  const zaDlugo = akcja.pole === 'nowy_termin' && nowyTermin && diffDays(nowyTermin, maxTermin) > 0
  const zaWczesnie = akcja.pole === 'nowy_termin' && nowyTermin && sprawa.termin && diffDays(nowyTermin, sprawa.termin) >= 0
  const wybor = akcja.tryb === 'wybor'

  function submit(e) {
    e.preventDefault()
    if (zaDlugo || zaWczesnie) return
    const dane = { typ: akcja.typ, data, inicjaly: inicjaly || null }
    if (akcja.pole === 'nowy_termin') dane.nowy_termin = nowyTermin
    if (akcja.pole === 'wydzialy') dane.payload = { wydzialy: wydzialy.split(',').map((x) => x.trim().toUpperCase()).filter(Boolean) }
    // wariant z przycisku, którym wysłano formularz: plik | ai | historia
    onZapisz(dane, e.nativeEvent.submitter?.value || 'historia')
  }

  return (
    <form className={wybor ? 'okno-tresc' : 'action-form'} onSubmit={submit}
      // w oknie wyboru Enter nie wybiera wariantu (domyślnie byłby to pierwszy przycisk – A)
      onKeyDown={(e) => wybor && e.key === 'Enter' && e.target.tagName === 'INPUT' && e.preventDefault()}>
      {wybor ? <h2>{akcja.label}</h2> : <strong>{akcja.label}</strong>}
      <label className="field">Data<input type="date" required max={todayISO()} value={data} onChange={(e) => setData(e.target.value)} /></label>
      {akcja.pole === 'nowy_termin' && (
        <label className="field">
          Nowy termin (maks. {formatPL(maxTermin)} – 2 miesiące od wpływu)
          <input type="date" required max={maxTermin} value={nowyTermin} onChange={(e) => setNowyTermin(e.target.value)} />
          {zaDlugo && <span className="txt-danger">Termin przekracza 2 miesiące od dnia wpływu (art. 13 ust. 2 UDIP).</span>}
          {zaWczesnie && <span className="txt-danger">Nowy termin musi być późniejszy niż obecny ({formatPL(sprawa.termin)}).</span>}
        </label>
      )}
      {akcja.pole === 'wydzialy' && (
        <label className="field">
          Wydziały (skróty, po przecinku)
          <input required value={wydzialy} onChange={(e) => setWydzialy(e.target.value)} placeholder="np. WGK, WE" />
        </label>
      )}
      <label className="field">Inicjały<input value={inicjaly} onChange={(e) => setInicjaly(e.target.value)} maxLength={10} /></label>
      {wybor ? (
        <>
          <p className="okno-pytanie">Jak przygotować dokument „{akcja.dokument.tytul}”?</p>
          <div className="warianty">
            <button type="submit" value="plik" className="wariant" disabled={!!(zaDlugo || zaWczesnie)}>
              <span className="wariant-litera">A</span>
              <strong>Prześlij plik</strong>
              <span className="hint">PDF, Word lub TXT → sprawdzenie tekstu → anonimizacja → zapis. Akcja zostanie odznaczona w historii.</span>
            </button>
            {akcja.dokument.draft && (
              <button type="submit" value="ai" className="wariant" disabled={!!(zaDlugo || zaWczesnie)}>
                <span className="wariant-litera">B</span>
                <strong>Zrób draft za pomocą AI</strong>
                <span className="hint">Projekt pisma z dokumentów wniosku i bazy wiedzy → poprawki → anonimizacja → zapis.</span>
              </button>
            )}
          </div>
          <p className="hint">Aplikacja niczego nie wysyła – tylko zapisuje, co zostało zrobione.</p>
          <div className="actions">
            <button type="button" className="btn" onClick={onAnuluj}>Anuluj</button>
            <button type="submit" value="historia" className="btn" disabled={!!(zaDlugo || zaWczesnie)}>
              Bez dokumentu – tylko zapisz w historii
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="hint">Aplikacja niczego nie wysyła – tylko zapisuje, co zostało zrobione.</p>
          <div className="actions">
            <button type="button" className="btn" onClick={onAnuluj}>Anuluj</button>
            <button type="submit" className="btn btn-primary" disabled={!!zaDlugo}>Zapisz</button>
          </div>
        </>
      )}
    </form>
  )
}

// Okno wyboru (modalne) dla akcji, które tworzą dokument. Esc / Anuluj zamyka bez zmian.
function OknoAkcji({ akcja, sprawa, onWybierz, onAnuluj }) {
  const okno = useRef(null)
  useEffect(() => {
    const d = okno.current
    if (d && !d.open) d.showModal()
    return () => d?.open && d.close()
  }, [])
  return (
    <dialog ref={okno} className="okno" aria-label={akcja.label}
      onCancel={(e) => { e.preventDefault(); onAnuluj() }}
      onClick={(e) => e.target === okno.current && onAnuluj()}>
      <FormularzAkcji akcja={akcja} sprawa={sprawa} onZapisz={onWybierz} onAnuluj={onAnuluj} />
    </dialog>
  )
}

// Opis wpisów audytowych (dodanie dokumentu, zmiany administratora) w historii sprawy.
const POLE = {
  rodzaj: 'rodzaj', nazwa_pliku: 'nazwa', wydzial: 'wydział', znak: 'znak', data_wplywu: 'data wpływu',
  wnioskodawca: 'wnioskodawca', przedmiot: 'przedmiot', inicjaly: 'osoba prowadząca',
}
const skroc = (v) => (v == null || v === '' ? '—' : String(v).length > 60 ? `${String(v).slice(0, 60)}…` : String(v))
function wartosc(pole, v) {
  if (pole === 'rodzaj') return RODZAJ_DOKUMENTU[v] || v
  if (pole === 'data_wplywu') return v ? formatPL(v) : '—'
  return skroc(v)
}

function OpisAudytu({ e }) {
  const p = e.payload || {}
  const zmiany = Object.entries(p.zmiany || {}).map(([pole, [stare, nowe]]) =>
    pole === 'tekst' ? `treść (${stare} → ${nowe} znaków)` : `${POLE[pole] || pole}: ${wartosc(pole, stare)} → ${wartosc(pole, nowe)}`)
  return (
    <>
      {p.dokument && <> „{p.dokument}”</>}
      {p.rodzaj && <> ({RODZAJ_DOKUMENTU[p.rodzaj] || p.rodzaj})</>}
      {zmiany.length > 0 && <span className="muted"> – {zmiany.join('; ')}</span>}
    </>
  )
}
const AUDYT = ['DOKUMENT_DODANIE', 'DOKUMENT_ZMIANA', 'DOKUMENT_USUNIECIE', 'SPRAWA_ZMIANA']

function PodobneSprawy({ sprawa }) {
  const [lista, setLista] = useState(null)
  const [blad, setBlad] = useState(null)
  const liczbaDok = sprawa.dokumenty.length

  useEffect(() => {
    let aktualne = true
    api.podobneSprawy(sprawa.id)
      .then((l) => aktualne && setLista(l))
      .catch((e) => aktualne && setBlad(e.message))
    return () => { aktualne = false }
  }, [sprawa.id, sprawa.przedmiot, liczbaDok])

  return (
    <div className="card">
      <h2>Podobne sprawy z archiwum</h2>
      {blad && <p className="txt-danger">{blad}</p>}
      {!lista && !blad && <p className="muted">Szukam w archiwum…</p>}
      {lista?.length === 0 && <p className="muted">Brak podobnych spraw w archiwum.</p>}
      <ul className="podobne">
        {lista?.map((p) => (
          <li key={p.id}>
            <div className="podobne-head">
              <Link to={`/sprawy/${p.id}`}>{p.znak}</Link>
              <span className="muted">{formatPL(p.data_wplywu)}</span>
              <StatusBadge status={p.status} />
              {p.ma_odpowiedz && <span className="pill pill-ok">jest odpowiedź</span>}
            </div>
            <div>{p.przedmiot}</div>
            {p.wydzialy.length > 0 && <div className="hint">Wydziały: {p.wydzialy.join(', ')}</div>}
            {p.fragment && <div className="fragment"><Podswietl tekst={p.fragment} /></div>}
          </li>
        ))}
      </ul>
    </div>
  )
}

function SugerowaneWydzialy({ sprawa, onPrzekaz, onLista }) {
  const [dane, setDane] = useState(null)
  const [blad, setBlad] = useState(null)
  const [wybrane, setWybrane] = useState([])
  const mozna = AKCJA.przekazanie.gdy.includes(sprawa.status)

  useEffect(() => {
    let aktualne = true
    api.sugestieWydzialow(sprawa.id)
      .then((d) => {
        if (!aktualne) return
        setDane(d)
        setWybrane(d.sugestie.slice(0, 1).map((s) => s.skrot))
        onLista(d.wszystkie)
      })
      .catch((e) => aktualne && setBlad(e.message))
    return () => { aktualne = false }
  }, [sprawa.id, sprawa.przedmiot, onLista])

  const przelacz = (skrot) => setWybrane((w) => (w.includes(skrot) ? w.filter((x) => x !== skrot) : [...w, skrot]))

  return (
    <div className="card">
      <h2>Sugerowane wydziały</h2>
      {blad && <p className="txt-danger">{blad}</p>}
      {!dane && !blad && <p className="muted">Analizuję wniosek…</p>}
      {dane?.sugestie.length === 0 && <p className="muted">Brak propozycji – wybierz wydział samodzielnie.</p>}
      <ul className="sugestie">
        {dane?.sugestie.map((s) => (
          <li key={s.skrot}>
            <label className="check">
              {mozna && <input type="checkbox" checked={wybrane.includes(s.skrot)} onChange={() => przelacz(s.skrot)} />}
              <span><strong>{s.skrot}</strong> – {s.nazwa}</span>
            </label>
            <div className="hint">
              <span className="pill pill-muted">{ZRODLO_SUGESTII[s.zrodlo] || s.zrodlo}</span> {s.uzasadnienie}
            </div>
          </li>
        ))}
      </ul>
      {mozna && dane?.sugestie.length > 0 && (
        <div className="actions">
          <button type="button" className="btn" disabled={!wybrane.length} onClick={() => onPrzekaz(wybrane)}>
            Przekazano do zaznaczonych…
          </button>
        </div>
      )}
      <p className="hint">Propozycje – decyzję podejmuje urzędnik. Lista jednostek wg BIP UM Bydgoszcz.</p>
    </div>
  )
}

// Dokument sprawy. Edycja (tekst, rodzaj, nazwa, wydział) i usuwanie – tylko administrator.
function Dokument({ dok, admin, onZapisz, onUsun }) {
  const [edycja, setEdycja] = useState(false)
  const [pola, setPola] = useState(null)
  const [blad, setBlad] = useState(null)
  const [usuwanie, setUsuwanie] = useState(false)
  const nazwa = bezRozszerzenia(dok.nazwa_pliku)
  const rodzaje = RODZAJE_W_SPRAWIE.includes(dok.rodzaj) ? RODZAJE_W_SPRAWIE : [dok.rodzaj, ...RODZAJE_W_SPRAWIE]

  async function docx() {
    setBlad(null)
    try {
      pobierzBlob(await api.pobierzDocx(dok.id), `${nazwa}.docx`)
    } catch (e) {
      setBlad(e.message)
    }
  }

  function edytuj() {
    setPola({ nazwa_pliku: dok.nazwa_pliku, rodzaj: dok.rodzaj, wydzial: dok.wydzial || '', tekst: dok.tekst })
    setEdycja(true)
  }

  const pole = (k) => ({ value: pola[k], onChange: (e) => setPola({ ...pola, [k]: e.target.value }) })

  return (
    <div className={`doc doc-${dok.rodzaj}`}>
      <div className="doc-head">
        <strong>{RODZAJ_DOKUMENTU[dok.rodzaj] || dok.rodzaj}</strong>
        <span className="muted">{dok.nazwa_pliku} · {METODA[dok.metoda] || dok.metoda}{dok.wydzial ? ` · ${dok.wydzial}` : ''}</span>
        {!edycja && (
          <span className="doc-buttons">
            <button className="btn btn-small" onClick={docx}>Pobierz .docx</button>
            <button className="btn btn-small" onClick={() => pobierzTekst(dok.tekst, `${nazwa}.txt`)}>Pobierz .txt</button>
            {admin && !usuwanie && (
              <>
                <button className="btn btn-small" onClick={edytuj}>Edytuj</button>
                <button className="btn btn-small btn-danger" onClick={() => setUsuwanie(true)}>Usuń</button>
              </>
            )}
            {admin && usuwanie && (
              <>
                <span className="hint">Usunąć dokument? Historia sprawy zostaje.</span>
                <button className="btn btn-small btn-danger" onClick={async () => { if (!(await onUsun(dok.id))) setUsuwanie(false) }}>Tak, usuń</button>
                <button className="btn btn-small" onClick={() => setUsuwanie(false)}>Nie</button>
              </>
            )}
          </span>
        )}
      </div>
      {blad && <p className="txt-danger">{blad}</p>}
      <OcrBaner dokument={dok} />
      {edycja ? (
        <>
          <div className="form-row">
            <label className="field">Nazwa pliku<input required maxLength={200} {...pole('nazwa_pliku')} /></label>
            <label className="field">Rodzaj
              <select {...pole('rodzaj')}>
                {rodzaje.map((r) => <option key={r} value={r}>{RODZAJ_DOKUMENTU[r] || r}</option>)}
              </select>
            </label>
            <label className="field">Wydział (skrót)<input maxLength={20} placeholder="np. WGK" {...pole('wydzial')} /></label>
          </div>
          <textarea className="doc-text" rows={14} aria-label="Treść dokumentu" {...pole('tekst')} />
          <p className="hint">Treść musi pozostać zanonimizowana – serwer odrzuci niezamazany PESEL lub numer dowodu.</p>
          <div className="actions">
            <button className="btn" onClick={() => setEdycja(false)}>Anuluj</button>
            <button className="btn btn-primary" disabled={!pola.nazwa_pliku.trim() || !pola.tekst.trim()}
              onClick={async () => { if (await onZapisz(dok.id, pola)) setEdycja(false) }}>Zapisz zmiany</button>
          </div>
        </>
      ) : (
        <pre className="doc-text readonly">{dok.tekst}</pre>
      )}
    </div>
  )
}

// Administrator: poprawa danych wniosku.
function EdycjaSprawy({ sprawa, onZapisz, onAnuluj }) {
  const [dane, setDane] = useState({
    znak: sprawa.znak, data_wplywu: sprawa.data_wplywu, wnioskodawca: sprawa.wnioskodawca,
    przedmiot: sprawa.przedmiot, inicjaly: sprawa.inicjaly || '',
  })
  const pole = (k) => ({ value: dane[k], onChange: (e) => setDane({ ...dane, [k]: e.target.value }) })
  return (
    <form className="action-form" onSubmit={(e) => { e.preventDefault(); onZapisz(dane) }}>
      <strong>Edycja danych wniosku</strong>
      <label className="field">Znak sprawy<input required pattern="BKS\.IV\.1431\.\d+\.\d{4}" {...pole('znak')} /></label>
      <label className="field">Data wpływu<input type="date" required max={todayISO()} {...pole('data_wplywu')} /></label>
      <label className="field">Wnioskodawca<input maxLength={300} {...pole('wnioskodawca')} /></label>
      <label className="field">Przedmiot<textarea rows={3} maxLength={2000} {...pole('przedmiot')} /></label>
      <label className="field">Osoba prowadząca (inicjały)<input maxLength={10} {...pole('inicjaly')} /></label>
      <p className="hint">Zmiana daty wpływu przelicza termin.</p>
      <div className="actions">
        <button type="button" className="btn" onClick={onAnuluj}>Anuluj</button>
        <button type="submit" className="btn btn-primary">Zapisz</button>
      </div>
    </form>
  )
}

// Administrator: zamknięcie sprawy (z powodem) albo jej wznowienie.
function ZamkniecieSprawy({ sprawa, onZapisz, onAnuluj }) {
  const [powod, setPowod] = useState('')
  const [data, setData] = useState(todayISO())
  const wznow = sprawa.status === 'ZAMKNIETA'
  return (
    <form className="action-form" onSubmit={(e) => {
      e.preventDefault()
      onZapisz(wznow ? { typ: 'WZNOWIENIE', data } : { typ: 'ZAMKNIECIE', data, payload: { powod } })
    }}>
      <strong>{wznow ? 'Wznów sprawę' : 'Zamknij sprawę'}</strong>
      <label className="field">Data<input type="date" required min={sprawa.data_wplywu} max={todayISO()} value={data} onChange={(e) => setData(e.target.value)} /></label>
      {wznow ? (
        <p className="hint">Sprawa wróci do statusu sprzed zamknięcia.</p>
      ) : (
        <label className="field">Powód zamknięcia
          <textarea required rows={2} maxLength={500} value={powod} onChange={(e) => setPowod(e.target.value)}
            placeholder="np. wniosek wycofany, zdublowana rejestracja" />
        </label>
      )}
      <div className="actions">
        <button type="button" className="btn" onClick={onAnuluj}>Anuluj</button>
        <button type="submit" className={`btn ${wznow ? 'btn-primary' : 'btn-danger'}`}>{wznow ? 'Wznów' : 'Zamknij sprawę'}</button>
      </div>
    </form>
  )
}

export default function Sprawa({ ja }) {
  const { id } = useParams()
  const [s, setS] = useState(null)
  const [blad, setBlad] = useState(null)
  const [akcja, setAkcja] = useState(null)      // formularz zdarzenia
  const [okno, setOkno] = useState(null)        // okno wyboru: plik / draft AI / tylko historia
  const [panel, setPanel] = useState(null)      // { typ: 'dokument', zadanie, cel, zdarzenie? } | { typ: 'projekt', zadanie, zdarzenie }
  const [jednostki, setJednostki] = useState([]) // lista wydziałów UMB (z sugestii)
  const [adminForm, setAdminForm] = useState(null) // 'edycja' | 'zamkniecie' (tylko administrator)
  const admin = ja?.rola === 'admin'
  const wyborPliku = useRef(null)
  const wyborCel = useRef(null)                 // co otworzyło wybór pliku: { cel, akcja?, zdarzenie? }
  const zapisanyDok = useRef(false)             // dokument już zapisany – przy ponowieniu tylko zdarzenie

  const wczytaj = useCallback(() => api.sprawa(id).then(setS).catch((e) => setBlad(e.message)), [id])
  useEffect(() => { wczytaj() }, [wczytaj])

  function wybierzPlik(cel, akcjaOkna = null, zdarzenie = null) {
    wyborCel.current = { cel, akcja: akcjaOkna, zdarzenie }
    wyborPliku.current?.click()
  }

  function wybrano(plik) {
    if (wyborPliku.current) wyborPliku.current.value = ''
    if (!plik) return
    const { cel, akcja: a, zdarzenie } = wyborCel.current
    setBlad(null)
    setAkcja(null)
    zapisanyDok.current = false
    const zadania = {
      'odp-wydzialu': { tytul: 'Odpowiedź wydziału', rodzaj: 'ODP_WYDZIALU', wydzialy: jednostki.length ? jednostki : null,
        przycisk: 'Zanonimizuj i zapisz odpowiedź wydziału' },
      dokument: { tytul: 'Nowy dokument', rodzaj: 'INNE', rodzaje: RODZAJE_W_SPRAWIE, przycisk: 'Zanonimizuj i zapisz' },
    }
    const zadanie = a
      ? { tytul: a.dokument.tytul, rodzaj: a.dokument.rodzaj, przycisk: `Zanonimizuj, zapisz i oznacz: ${a.label}` }
      : zadania[cel]
    setPanel({ typ: 'dokument', cel, zdarzenie, zadanie: { plik, ...zadanie } })
  }

  async function zapiszZdarzenieWPanelu(dane) {
    try {
      await api.dodajZdarzenie(id, { data: todayISO(), inicjaly: s.inicjaly || null, ...dane })
    } catch (e) {
      throw new Error(`Dokument zapisano, ale nie zapisano zdarzenia w historii: ${e.message}`, { cause: e })
    }
  }

  async function zapiszDokument(plikTxt, { rodzaj, wydzial }) {
    if (!zapisanyDok.current) {
      await api.dodajDokument(id, plikTxt, rodzaj, wydzial)
      zapisanyDok.current = true
    }
    if (panel.cel === 'odp-wydzialu') await zapiszZdarzenieWPanelu({ typ: 'ODP_WYDZIALU', payload: { wydzial } })
    if (panel.zdarzenie) await zapiszZdarzenieWPanelu(panel.zdarzenie)  // akcja z okna wyboru – odznaczenie
    setPanel(null)
    await wczytaj()
  }

  async function zapiszProjekt(zanonimizowany) {
    const { dokument } = panel.akcja
    if (!zapisanyDok.current) {
      await api.dodajDokument(id, jakoPlikTxt(`${dokument.tytul} - ${s.znak}`, zanonimizowany),
        dokument.rodzajDraftu || dokument.rodzaj)
      zapisanyDok.current = true
    }
    await zapiszZdarzenieWPanelu(panel.zdarzenie)
    setPanel(null)
    await wczytaj()
  }

  // Okno wyboru: A – plik, B – draft AI, albo samo zdarzenie w historii (dane: data, inicjały, wydziały, termin)
  function wybierzWariant(a, dane, wariant) {
    setOkno(null)
    if (wariant === 'historia') return zapiszZdarzenie(dane)
    if (wariant === 'plik') return wybierzPlik(a.id, a, dane)
    zapisanyDok.current = false
    setAkcja(null)
    setPanel({
      typ: 'projekt', akcja: a, zdarzenie: dane,
      zadanie: { tytul: a.dokument.tytul, rodzaj: a.dokument.draft, wydzialy: dane.payload?.wydzialy,
        nowy_termin: dane.nowy_termin, przycisk: `Zatwierdź i oznacz: ${a.label}` },
    })
  }

  async function zapiszZdarzenie(dane) {
    setBlad(null)
    try {
      await api.dodajZdarzenie(id, dane)
      setAkcja(null)
      await wczytaj()
    } catch (e) {
      setBlad(e.message)
    }
  }

  // akcje administratora: true = udało się (formularz / potwierdzenie może się zamknąć)
  async function adminAkcja(fn) {
    setBlad(null)
    try {
      await fn()
      await wczytaj()
      return true
    } catch (e) {
      setBlad(e.message)
      return false
    }
  }

  const zapiszDokumentAdmin = (dokId, pola) => adminAkcja(() => api.edytujDokument(dokId, pola))
  const usunDokument = (dokId) => adminAkcja(() => api.usunDokument(dokId))
  const zapiszSprawe = async (pola) => { if (await adminAkcja(() => api.edytujSprawe(id, pola))) setAdminForm(null) }
  const zamknijSprawe = async (dane) => {
    if (await adminAkcja(() => api.dodajZdarzenie(id, { inicjaly: ja.login.slice(0, 20), ...dane }))) setAdminForm(null)
  }

  function kliknij(a) {
    if (a.tryb === 'plik') wybierzPlik(a.id)
    else if (a.tryb === 'wybor') { setAkcja(null); setOkno(a) }
    else setAkcja(a)
  }

  if (!s) return blad ? <div className="card error" role="alert">{blad}</div> : <p className="muted">Wczytywanie…</p>

  const dostepne = AKCJE.filter((a) => a.gdy.includes(s.status))
  const zajete = !!panel

  return (
    <section>
      <p><Link to="/">← Kalendarz</Link></p>
      <div className="page-head">
        <h1>{s.znak}</h1>
        <div className="head-badges">
          <StatusBadge status={s.status} przedluzenieDni={s.przedluzenie_dni} />
          <PilnoscBadge pilnosc={s.pilnosc} />
        </div>
      </div>
      {blad && <div className="card error" role="alert">{blad}</div>}

      <div className="grid-2">
        <div className="card">
          <h2>Dane sprawy</h2>
          <dl className="dl">
            <dt>Wnioskodawca</dt><dd>{s.wnioskodawca || '—'}</dd>
            <dt>Przedmiot</dt><dd>{s.przedmiot || '—'}</dd>
            <dt>Data wpływu</dt><dd>{formatPL(s.data_wplywu)}</dd>
            <dt>Termin</dt>
            <dd>
              {s.termin_wstrzymany ? 'wstrzymany (oczekiwanie na doprecyzowanie)' : formatPL(s.termin)}
              {s.pozostalo_dni != null && <span className="muted"> · pozostało {s.pozostalo_dni} dni</span>}
            </dd>
            <dt>Data odpowiedzi</dt><dd>{formatPL(s.data_odpowiedzi)}</dd>
            <dt>Osoba prowadząca</dt><dd>{s.inicjaly || '—'}</dd>
          </dl>
          {admin && s.zrodlo !== 'import' && (
            adminForm === 'edycja' ? (
              <EdycjaSprawy sprawa={s} onZapisz={zapiszSprawe} onAnuluj={() => setAdminForm(null)} />
            ) : adminForm === 'zamkniecie' ? (
              <ZamkniecieSprawy sprawa={s} onZapisz={zamknijSprawe} onAnuluj={() => setAdminForm(null)} />
            ) : (
              <div className="action-buttons admin-akcje">
                <span className="pill pill-muted">Administrator</span>
                <button type="button" className="btn btn-small" onClick={() => setAdminForm('edycja')}>Edytuj dane wniosku</button>
                {s.status === 'ZAMKNIETA' ? (
                  <button type="button" className="btn btn-small" onClick={() => setAdminForm('zamkniecie')}>Wznów sprawę</button>
                ) : !['WYSLANA', 'BEZ_ROZPOZNANIA'].includes(s.status) && (
                  <button type="button" className="btn btn-small btn-danger" onClick={() => setAdminForm('zamkniecie')}>Zamknij sprawę</button>
                )}
              </div>
            )
          )}
          <h3>Uwagi do danych</h3>
          <Flagi flagi={s.flagi} />
        </div>

        <div className="card">
          <h2>Co dalej?</h2>
          {akcja ? (
            <FormularzAkcji key={akcja.id + (akcja.wydzialy || []).join()} akcja={akcja} sprawa={s}
              onZapisz={zapiszZdarzenie} onAnuluj={() => setAkcja(null)} />
          ) : dostepne.length ? (
            <div className="action-buttons">
              {dostepne.map((a) => (
                <button key={a.id} className={`btn ${a.glowna ? 'btn-primary' : ''}`}
                  disabled={zajete && a.tryb !== 'formularz'} onClick={() => kliknij(a)}>{a.label}</button>
              ))}
            </div>
          ) : (
            <p className="muted">Sprawa zamknięta.</p>
          )}

          <h3>Historia</h3>
          <ol className="timeline">
            {(s.zdarzenia || []).map((e) => (
              <li key={e.id} className={AUDYT.includes(e.typ) ? 'audyt' : undefined}>
                <span className="nowrap">{formatPL(e.data)}</span> – {ZDARZENIE[e.typ] || e.typ}
                {e.nowy_termin && <> → nowy termin {formatPL(e.nowy_termin)}</>}
                {e.payload?.wydzialy?.length > 0 && <> ({e.payload.wydzialy.join(', ')})</>}
                {e.payload?.wydzial && <> ({e.payload.wydzial})</>}
                {e.payload?.powod && <> – {e.payload.powod}</>}
                {AUDYT.includes(e.typ) && <OpisAudytu e={e} />}
                {e.inicjaly && <span className="muted"> · {e.inicjaly}</span>}
              </li>
            ))}
          </ol>
        </div>
      </div>

      <input ref={wyborPliku} type="file" accept={AKCEPTOWANE} hidden onChange={(e) => wybrano(e.target.files[0])} />
      {panel?.typ === 'dokument' && (
        <NowyDokument key={`${panel.cel}-${panel.zadanie.plik.name}-${panel.zadanie.plik.lastModified}`}
          zadanie={panel.zadanie} wnioskodawca={s.wnioskodawca} onZapisz={zapiszDokument} onAnuluj={() => setPanel(null)} />
      )}
      {panel?.typ === 'projekt' && (
        <ProjektPisma key={panel.akcja.id} sprawa={s} zadanie={panel.zadanie} onZapisz={zapiszProjekt} onAnuluj={() => setPanel(null)} />
      )}
      {okno && (
        <OknoAkcji key={okno.id + (okno.wydzialy || []).join()} akcja={okno} sprawa={s}
          onWybierz={(dane, wariant) => wybierzWariant(okno, dane, wariant)} onAnuluj={() => setOkno(null)} />
      )}

      <div className="grid-2">
        <PodobneSprawy sprawa={s} />
        <SugerowaneWydzialy sprawa={s} onLista={setJednostki}
          onPrzekaz={(wydzialy) => { setAkcja(null); setOkno({ ...AKCJA.przekazanie, wydzialy }) }} />
      </div>

      <div className="card">
        <div className="doc-head">
          <h2>Dokumenty</h2>
          <button type="button" className="btn btn-primary" disabled={zajete} onClick={() => wybierzPlik('dokument')}>Dodaj dokument</button>
        </div>
        {s.dokumenty?.length ? (
          s.dokumenty.map((dok) => (
            <Dokument key={`${dok.id}-${dok.tekst.length}-${dok.rodzaj}-${dok.nazwa_pliku}`} dok={dok} admin={admin}
              onZapisz={zapiszDokumentAdmin} onUsun={usunDokument} />
          ))
        ) : (
          <p className="muted">Brak dokumentów w sprawie.</p>
        )}
      </div>
    </section>
  )
}
