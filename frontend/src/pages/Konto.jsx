// Ustawienia własnego konta: hasło, aplikacja TOTP, klucze sprzętowe.
import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { KonfiguracjaKlucza, KonfiguracjaTotp } from '../components/Konfiguracja2FA'
import ZmianaHasla from '../components/ZmianaHasla'
import { formatPL } from '../lib/dates'

export default function Konto({ ja, onZmiana }) {
  const [klucze, setKlucze] = useState([])
  const [blad, setBlad] = useState(null)
  const [info, setInfo] = useState(null)
  const [nowyTotp, setNowyTotp] = useState(false)
  const [nowyKlucz, setNowyKlucz] = useState(false)

  const odswiez = useCallback(() => api.klucze().then(setKlucze).catch((e) => setBlad(e.message)), [])
  useEffect(() => { odswiez() }, [odswiez])

  async function akcja(fn, komunikat) {
    setBlad(null)
    setInfo(null)
    try {
      const wynik = await fn()
      if (wynik) onZmiana(wynik)
      setInfo(komunikat)
      await odswiez()
    } catch (err) {
      setBlad(err.message)
    }
  }

  const gotowe = (komunikat) => (wynik) => {
    onZmiana(wynik)
    setNowyTotp(false)
    setNowyKlucz(false)
    setInfo(komunikat)
    odswiez()
  }

  return (
    <section>
      <div className="page-head"><h1>Moje konto – {ja.login}</h1></div>
      {info && <p className="banner-info inline-banner" role="status">{info}</p>}
      {blad && <p className="txt-danger" role="alert">{blad}</p>}

      <div className="grid-2">
        <div className="card">
          <h2>Hasło</h2>
          <p className="hint">Po zmianie hasła pozostałe sesje (inne urządzenia) zostaną wylogowane.</p>
          <ZmianaHasla minDlugosc={ja.min_dlugosc_hasla} onGotowe={gotowe('Hasło zmienione.')} />
        </div>

        <div className="card">
          <h2>Aplikacja uwierzytelniająca</h2>
          <p>{ja.totp ? <span className="pill pill-ok">Włączona</span> : <span className="pill pill-muted">Wyłączona</span>}</p>
          {nowyTotp ? (
            <>
              <KonfiguracjaTotp onGotowe={gotowe('Aplikacja uwierzytelniająca skonfigurowana.')} />
              <button type="button" className="btn btn-small" onClick={() => setNowyTotp(false)}>Anuluj</button>
            </>
          ) : (
            <div className="action-buttons">
              <button type="button" className="btn" onClick={() => setNowyTotp(true)}>
                {ja.totp ? 'Przenieś na nowy telefon' : 'Włącz'}
              </button>
              {ja.totp && (
                <button type="button" className="btn" onClick={() => window.confirm('Wyłączyć logowanie kodem z aplikacji?')
                  && akcja(api.totpWylacz, 'Aplikacja uwierzytelniająca wyłączona.')}>Wyłącz</button>
              )}
            </div>
          )}

          <h2>Klucze sprzętowe</h2>
          {klucze.length === 0 && <p className="muted">Brak kluczy.</p>}
          <ul className="lista-kluczy">
            {klucze.map((k) => (
              <li key={k.id}>
                <strong>{k.nazwa}</strong> <span className="muted">dodany {formatPL(k.utworzono.slice(0, 10))}</span>
                <button type="button" className="btn btn-small" onClick={() => window.confirm(`Usunąć klucz „${k.nazwa}”?`)
                  && akcja(() => api.usunKlucz(k.id), 'Klucz usunięty.')}>Usuń</button>
              </li>
            ))}
          </ul>
          {nowyKlucz ? (
            <>
              <KonfiguracjaKlucza onGotowe={gotowe('Klucz dodany.')} />
              <button type="button" className="btn btn-small" onClick={() => setNowyKlucz(false)}>Anuluj</button>
            </>
          ) : (
            <button type="button" className="btn" onClick={() => setNowyKlucz(true)}>Dodaj klucz</button>
          )}
          {ja.wymagaj_2fa && <p className="hint">Drugi składnik jest obowiązkowy – ostatniego nie można usunąć.</p>}
        </div>
      </div>
    </section>
  )
}
