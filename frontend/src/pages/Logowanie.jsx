// Logowanie w krokach (stan z backendu): hasło -> DRUGI_SKLADNIK -> ZMIEN_HASLO -> KONFIGURUJ_2FA -> OK.
import { useState } from 'react'
import { api } from '../api/client'
import Konfiguracja2FA from '../components/Konfiguracja2FA'
import ZmianaHasla from '../components/ZmianaHasla'
import { bladKlucza, kluczeDostepne, uzyjKlucza } from '../lib/webauthn'

function Haslo({ onZalogowano }) {
  const [login, setLogin] = useState('')
  const [haslo, setHaslo] = useState('')
  const [blad, setBlad] = useState(null)
  const [trwa, setTrwa] = useState(false)

  async function wyslij(e) {
    e.preventDefault()
    setBlad(null)
    setTrwa(true)
    try {
      onZalogowano(await api.zaloguj(login, haslo))
    } catch (err) {
      setBlad(err.message)
      setHaslo('')
    } finally {
      setTrwa(false)
    }
  }

  return (
    <form onSubmit={wyslij}>
      <h1>Logowanie</h1>
      <label className="field">Login
        <input autoComplete="username" required value={login} onChange={(e) => setLogin(e.target.value)} autoFocus />
      </label>
      <label className="field">Hasło
        <input type="password" autoComplete="current-password" required value={haslo} onChange={(e) => setHaslo(e.target.value)} />
      </label>
      {blad && <p className="txt-danger" role="alert">{blad}</p>}
      <button type="submit" className="btn btn-primary btn-pelny" disabled={trwa}>{trwa ? 'Loguję…' : 'Zaloguj się'}</button>
    </form>
  )
}

function DrugiSkladnik({ ja, onGotowe }) {
  const [kod, setKod] = useState('')
  const [blad, setBlad] = useState(null)
  const [trwa, setTrwa] = useState(false)
  const klucz = ja.klucze > 0 && kluczeDostepne()

  async function zKodem(e) {
    e.preventDefault()
    setBlad(null)
    setTrwa(true)
    try {
      onGotowe(await api.totpWeryfikuj(kod))
    } catch (err) {
      setBlad(err.message)
      setKod('')
    } finally {
      setTrwa(false)
    }
  }

  async function zKluczem() {
    setBlad(null)
    setTrwa(true)
    try {
      onGotowe(await api.kluczLogowanie(await uzyjKlucza(await api.kluczLogowanieOpcje())))
    } catch (err) {
      setBlad(err instanceof DOMException ? bladKlucza(err) : err.message)
    } finally {
      setTrwa(false)
    }
  }

  return (
    <div>
      <h1>Potwierdź logowanie</h1>
      {ja.totp && (
        <form onSubmit={zKodem}>
          <label className="field">Kod z aplikacji uwierzytelniającej
            <input inputMode="numeric" autoComplete="one-time-code" pattern="[0-9 ]{6,7}" maxLength={7} required
              value={kod} onChange={(e) => setKod(e.target.value)} autoFocus />
          </label>
          <button type="submit" className="btn btn-primary btn-pelny" disabled={trwa}>Potwierdź</button>
        </form>
      )}
      {ja.totp && klucz && <p className="lub">albo</p>}
      {klucz && (
        <button type="button" className="btn btn-pelny" onClick={zKluczem} disabled={trwa}>
          {trwa ? 'Dotknij klucza…' : 'Użyj klucza sprzętowego'}
        </button>
      )}
      {!ja.totp && ja.klucze > 0 && !kluczeDostepne() && (
        <p className="txt-danger">Konto używa klucza sprzętowego, a ta strona nie jest otwarta przez HTTPS ani localhost.</p>
      )}
      {blad && <p className="txt-danger" role="alert">{blad}</p>}
      <p className="hint">Nie masz dostępu do telefonu ani klucza? Administrator może zresetować drugi składnik.</p>
    </div>
  )
}

export default function Logowanie({ ja, onZmiana }) {
  async function anuluj() {
    await api.wyloguj().catch(() => {})
    onZmiana(null)
  }

  let tresc
  if (!ja) tresc = <Haslo onZalogowano={onZmiana} />
  else if (ja.stan === 'DRUGI_SKLADNIK') tresc = <DrugiSkladnik ja={ja} onGotowe={onZmiana} />
  else if (ja.stan === 'ZMIEN_HASLO') {
    tresc = (
      <div>
        <h1>Ustaw nowe hasło</h1>
        <p className="hint">Hasło jest tymczasowe – przed rozpoczęciem pracy ustaw własne.</p>
        <ZmianaHasla minDlugosc={ja.min_dlugosc_hasla} onGotowe={onZmiana} przycisk="Zapisz i kontynuuj" />
      </div>
    )
  } else if (ja.stan === 'KONFIGURUJ_2FA') {
    tresc = (
      <div>
        <h1>Dodaj drugi składnik logowania</h1>
        <p className="hint">Przy każdym logowaniu oprócz hasła potwierdzisz tożsamość kodem z telefonu albo kluczem.</p>
        <Konfiguracja2FA onGotowe={onZmiana} />
      </div>
    )
  }

  return (
    <div className="auth-wrap">
      <div className="auth-card card">
        <div className="brand auth-brand">
          <img className="brand-logo" src="/logo.png" alt="Bydgoszcz" />
          <div>
            <div className="brand-title">Asystent urzędnika</div>
            <div className="brand-sub">Urząd Miasta Bydgoszczy · Biuro Komunikacji Społecznej</div>
          </div>
        </div>
        {tresc}
        {ja && (
          <p className="auth-stopka">
            Zalogowano jako <strong>{ja.login}</strong> ·{' '}
            <button type="button" className="link" onClick={anuluj}>Wyloguj</button>
          </p>
        )}
      </div>
    </div>
  )
}
