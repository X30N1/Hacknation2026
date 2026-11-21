import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { Flagi, PilnoscBadge, StatusBadge } from '../components/Badges'
import { formatPL, weekdayPL } from '../lib/dates'

function Pozostalo({ s }) {
  if (s.termin_wstrzymany) return <span className="muted" title="Bieg terminu wstrzymany do czasu doprecyzowania">wstrzymany</span>
  if (s.pozostalo_dni === null || s.pozostalo_dni === undefined) return <span className="muted">—</span>
  if (s.pozostalo_dni < 0) return <strong className="txt-danger">{s.pozostalo_dni} dni</strong>
  return <span>{s.pozostalo_dni} dni</span>
}

function Podsumowanie({ sprawy }) {
  const licz = (p) => sprawy.filter((s) => s.pilnosc === p).length
  const otwarte = sprawy.filter((s) => s.pilnosc !== 'ZAMKNIETA').length
  const kafle = [
    { k: 'PRZEKROCZONY', label: 'Po terminie', n: licz('PRZEKROCZONY') },
    { k: 'DZIS', label: 'Termin dziś', n: licz('DZIS') },
    { k: 'JUTRO', label: 'Termin jutro', n: licz('JUTRO') },
    { k: 'OTWARTE', label: 'Otwarte sprawy', n: otwarte },
  ]
  return (
    <div className="stats" role="list">
      {kafle.map((x) => (
        <div key={x.k} className={`stat stat-${x.k}`} role="listitem">
          <div className="stat-n">{x.n}</div>
          <div className="stat-label">{x.label}</div>
        </div>
      ))}
    </div>
  )
}

function Legenda() {
  return (
    <div className="legend" aria-label="Legenda kolorów">
      <span><i className="sw sw-PRZEKROCZONY" /> po terminie</span>
      <span><i className="sw sw-DZIS" /> termin dziś</span>
      <span><i className="sw sw-JUTRO" /> termin jutro</span>
      <span><i className="sw sw-WKROTCE" /> do 3 dni</span>
      <span><i className="sw sw-ZAMKNIETA" /> zamknięte</span>
    </div>
  )
}

export default function Kalendarz() {
  const [sprawy, setSprawy] = useState(null)
  const [blad, setBlad] = useState(null)
  const [rok, setRok] = useState('')
  const [tylkoOtwarte, setTylkoOtwarte] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    api.sprawy().then(setSprawy).catch((e) => setBlad(e.message))
  }, [])

  const lata = useMemo(() => [...new Set((sprawy || []).map((s) => s.rok))].sort((a, b) => b - a), [sprawy])

  const widoczne = useMemo(() => {
    if (!sprawy) return []
    return sprawy
      .filter((s) => !rok || String(s.rok) === rok)
      .filter((s) => !tylkoOtwarte || s.pilnosc !== 'ZAMKNIETA')
      .sort((a, b) => a.data_wplywu.localeCompare(b.data_wplywu) || a.nr - b.nr)
  }, [sprawy, rok, tylkoOtwarte])

  if (blad) return <div className="card error" role="alert">{blad}</div>
  if (!sprawy) return <p className="muted">Wczytywanie wniosków…</p>

  return (
    <section>
      <div className="page-head">
        <h1>Kalendarz wniosków</h1>
        <Link to="/nowy" className="btn btn-primary">+ Zarejestruj wniosek</Link>
      </div>

      <Podsumowanie sprawy={sprawy} />

      <div className="toolbar">
        <label>
          Rok:{' '}
          <select value={rok} onChange={(e) => setRok(e.target.value)}>
            <option value="">wszystkie</option>
            {lata.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </label>
        <label className="check">
          <input type="checkbox" checked={tylkoOtwarte} onChange={(e) => setTylkoOtwarte(e.target.checked)} /> tylko otwarte
        </label>
        <span className="muted">Kolejność: od najstarszego wpływu · {widoczne.length} wniosków</span>
        <Legenda />
      </div>

      <div className="table-wrap">
        <table className="cal">
          <thead>
            <tr>
              <th>Lp.</th>
              <th>Nr sprawy</th>
              <th>Wnioskodawca</th>
              <th>Przedmiot</th>
              <th>Wpływ</th>
              <th>Termin</th>
              <th>Pozostało</th>
              <th>Odpowiedź</th>
              <th>Osoba</th>
              <th>Status</th>
              <th aria-label="Uwagi do danych">⚠</th>
            </tr>
          </thead>
          <tbody>
            {widoczne.map((s, i) => (
              <tr
                key={s.id}
                className={`row row-${s.pilnosc}`}
                onClick={() => navigate(`/sprawy/${s.id}`)}
                tabIndex={0}
                onKeyDown={(e) => e.key === 'Enter' && navigate(`/sprawy/${s.id}`)}
              >
                <td>{i + 1}</td>
                <td className="nowrap"><Link to={`/sprawy/${s.id}`} onClick={(e) => e.stopPropagation()}>{s.znak}</Link></td>
                <td>{s.wnioskodawca || <span className="muted">—</span>}</td>
                <td className="przedmiot" title={s.przedmiot}>{s.przedmiot}</td>
                <td className="nowrap">{formatPL(s.data_wplywu)}</td>
                <td className="nowrap">
                  {s.termin ? <>{formatPL(s.termin)} <span className="muted">{weekdayPL(s.termin)}</span></> : <span className="muted">—</span>}
                  <div><PilnoscBadge pilnosc={s.pilnosc} /></div>
                </td>
                <td className="nowrap"><Pozostalo s={s} /></td>
                <td className="nowrap">{formatPL(s.data_odpowiedzi)}</td>
                <td>{s.inicjaly || <span className="muted">—</span>}</td>
                <td><StatusBadge status={s.status} przedluzenieDni={s.przedluzenie_dni} /></td>
                <td><Flagi flagi={s.flagi} compact /></td>
              </tr>
            ))}
            {!widoczne.length && (
              <tr><td colSpan={11} className="muted center">Brak wniosków dla wybranych filtrów.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}
