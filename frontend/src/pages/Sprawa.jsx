import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { Flagi, PilnoscBadge, StatusBadge } from '../components/Badges'
import { addDays, addMonths, diffDays, formatPL, todayISO } from '../lib/dates'
import { METODA, ZDARZENIE } from '../lib/labels'
import OcrBaner from '../components/OcrBaner'

// Akcje dostępne w danym statusie. `pole` = dodatkowe dane w formularzu.
const AKCJE = [
  { typ: 'PRZEKAZANIE', label: 'Przekazano do wydziałów', pole: 'wydzialy', gdy: ['NOWY', 'W_WYDZIALACH', 'PRZEDLUZONA'] },
  { typ: 'WEZWANIE_DOPRECYZOWANIE', label: 'Wezwanie do doprecyzowania', gdy: ['NOWY', 'W_WYDZIALACH'] },
  { typ: 'DOPRECYZOWANIE_OTRZYMANE', label: 'Otrzymano doprecyzowanie', gdy: ['DOPRECYZOWANIE'] },
  { typ: 'PRZEDLUZENIE', label: 'Przedłuż termin (kwerenda)', pole: 'nowy_termin', gdy: ['NOWY', 'W_WYDZIALACH', 'PRZEDLUZONA'] },
  { typ: 'PROJEKT', label: 'Odpowiedź przygotowana', gdy: ['W_WYDZIALACH', 'PRZEDLUZONA'] },
  { typ: 'WYSLANO', label: 'Oznacz jako wysłaną', gdy: ['PROJEKT_GOTOWY'] },
  { typ: 'BEZ_ROZPOZNANIA', label: 'Pozostaw bez rozpoznania', gdy: ['DOPRECYZOWANIE'] },
]

function FormularzAkcji({ akcja, sprawa, onZapisz, onAnuluj }) {
  const [data, setData] = useState(todayISO())
  const [nowyTermin, setNowyTermin] = useState(sprawa.termin ? addDays(sprawa.termin, 14) : '')
  const [wydzialy, setWydzialy] = useState('')
  const [inicjaly, setInicjaly] = useState(sprawa.inicjaly || '')
  const maxTermin = addMonths(sprawa.data_wplywu, 2)
  const zaDlugo = akcja.pole === 'nowy_termin' && nowyTermin && diffDays(nowyTermin, maxTermin) > 0

  function submit(e) {
    e.preventDefault()
    const dane = { typ: akcja.typ, data, inicjaly: inicjaly || null }
    if (akcja.pole === 'nowy_termin') dane.nowy_termin = nowyTermin
    if (akcja.pole === 'wydzialy') dane.payload = { wydzialy: wydzialy.split(',').map((x) => x.trim()).filter(Boolean) }
    onZapisz(dane)
  }

  return (
    <form className="action-form" onSubmit={submit}>
      <strong>{akcja.label}</strong>
      <label className="field">Data<input type="date" required value={data} onChange={(e) => setData(e.target.value)} /></label>
      {akcja.pole === 'nowy_termin' && (
        <label className="field">
          Nowy termin (maks. {formatPL(maxTermin)} – 2 miesiące od wpływu)
          <input type="date" required value={nowyTermin} onChange={(e) => setNowyTermin(e.target.value)} />
          {zaDlugo && <span className="txt-danger">Termin przekracza 2 miesiące od dnia wpływu (art. 13 ust. 2 UDIP).</span>}
        </label>
      )}
      {akcja.pole === 'wydzialy' && (
        <label className="field">
          Wydziały (skróty, po przecinku)
          <input required value={wydzialy} onChange={(e) => setWydzialy(e.target.value)} placeholder="np. WGK, WE" />
        </label>
      )}
      <label className="field">Inicjały<input value={inicjaly} onChange={(e) => setInicjaly(e.target.value)} maxLength={10} /></label>
      <p className="hint">Aplikacja niczego nie wysyła – tylko zapisuje, co zostało zrobione.</p>
      <div className="actions">
        <button type="button" className="btn" onClick={onAnuluj}>Anuluj</button>
        <button type="submit" className="btn btn-primary">Zapisz</button>
      </div>
    </form>
  )
}

function Dokument({ dok, onZapisz }) {
  const [edycja, setEdycja] = useState(false)
  const [tekst, setTekst] = useState(dok.tekst)
  return (
    <div className="doc">
      <div className="doc-head">
        <strong>{dok.nazwa_pliku}</strong>
        <span className="muted">{dok.rodzaj} · {METODA[dok.metoda] || dok.metoda}{dok.wydzial ? ` · ${dok.wydzial}` : ''}</span>
        {!edycja && <button className="btn btn-small" onClick={() => setEdycja(true)}>Popraw tekst</button>}
      </div>
      <OcrBaner dokument={dok} />
      {edycja ? (
        <>
          <textarea className="doc-text" rows={14} value={tekst} onChange={(e) => setTekst(e.target.value)} />
          <div className="actions">
            <button className="btn" onClick={() => { setTekst(dok.tekst); setEdycja(false) }}>Anuluj</button>
            <button className="btn btn-primary" onClick={async () => { await onZapisz(dok.id, tekst); setEdycja(false) }}>Zapisz tekst</button>
          </div>
        </>
      ) : (
        <pre className="doc-text readonly">{dok.tekst}</pre>
      )}
    </div>
  )
}

export default function Sprawa() {
  const { id } = useParams()
  const [s, setS] = useState(null)
  const [blad, setBlad] = useState(null)
  const [akcja, setAkcja] = useState(null)

  const wczytaj = useCallback(() => api.sprawa(id).then(setS).catch((e) => setBlad(e.message)), [id])
  useEffect(() => { wczytaj() }, [wczytaj])

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

  async function zapiszTekst(dokId, tekst) {
    try {
      await api.poprawTekst(dokId, tekst)
      await wczytaj()
    } catch (e) {
      setBlad(e.message)
    }
  }

  if (!s) return blad ? <div className="card error" role="alert">{blad}</div> : <p className="muted">Wczytywanie…</p>

  const dostepne = AKCJE.filter((a) => a.gdy.includes(s.status))

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
          <h3>Uwagi do danych</h3>
          <Flagi flagi={s.flagi} />
        </div>

        <div className="card">
          <h2>Co dalej?</h2>
          {akcja ? (
            <FormularzAkcji akcja={akcja} sprawa={s} onZapisz={zapiszZdarzenie} onAnuluj={() => setAkcja(null)} />
          ) : dostepne.length ? (
            <div className="action-buttons">
              {dostepne.map((a) => (
                <button key={a.typ} className="btn" onClick={() => setAkcja(a)}>{a.label}</button>
              ))}
            </div>
          ) : (
            <p className="muted">Sprawa zamknięta.</p>
          )}

          <h3>Historia</h3>
          <ol className="timeline">
            {(s.zdarzenia || []).map((e) => (
              <li key={e.id}>
                <span className="nowrap">{formatPL(e.data)}</span> – {ZDARZENIE[e.typ] || e.typ}
                {e.nowy_termin && <> → nowy termin {formatPL(e.nowy_termin)}</>}
                {e.payload?.wydzialy?.length > 0 && <> ({e.payload.wydzialy.join(', ')})</>}
                {e.inicjaly && <span className="muted"> · {e.inicjaly}</span>}
              </li>
            ))}
          </ol>
        </div>
      </div>

      <div className="grid-2">
        <div className="card">
          <h2>Podobne sprawy z archiwum</h2>
          <p className="muted">W przygotowaniu – wyszukiwanie po treści wniosku.</p>
        </div>
        <div className="card">
          <h2>Sugerowane wydziały</h2>
          <p className="muted">W przygotowaniu – propozycje z uzasadnieniem.</p>
        </div>
      </div>

      <div className="card">
        <h2>Dokumenty</h2>
        {s.dokumenty?.length ? (
          s.dokumenty.map((dok) => <Dokument key={dok.id} dok={dok} onZapisz={zapiszTekst} />)
        ) : (
          <p className="muted">Brak dokumentów w sprawie.</p>
        )}
      </div>
    </section>
  )
}
