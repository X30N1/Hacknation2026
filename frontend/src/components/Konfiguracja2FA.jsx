// Dodanie drugiego składnika logowania: aplikacja TOTP (kod QR) albo klucz sprzętowy (FIDO2).
import { useState } from 'react'
import { api } from '../api/client'
import { bladKlucza, kluczeDostepne, zarejestrujKlucz } from '../lib/webauthn'

export function KonfiguracjaTotp({ onGotowe }) {
  const [qr, setQr] = useState(null)
  const [kod, setKod] = useState('')
  const [blad, setBlad] = useState(null)
  const [trwa, setTrwa] = useState(false)

  async function generuj() {
    setBlad(null)
    try {
      setQr(await api.totpNowy())
    } catch (err) {
      setBlad(err.message)
    }
  }

  async function potwierdz(e) {
    e.preventDefault()
    setBlad(null)
    setTrwa(true)
    try {
      onGotowe(await api.totpPotwierdz(kod))
    } catch (err) {
      setBlad(err.message)
    } finally {
      setTrwa(false)
    }
  }

  if (!qr) {
    return (
      <div>
        <p className="hint">Google Authenticator, Microsoft Authenticator, Aegis, FreeOTP albo menedżer haseł.</p>
        <button type="button" className="btn btn-primary" onClick={generuj}>Pokaż kod QR</button>
        {blad && <p className="txt-danger">{blad}</p>}
      </div>
    )
  }
  return (
    <form onSubmit={potwierdz}>
      <ol className="kroki">
        <li>Zeskanuj kod aplikacją uwierzytelniającą.</li>
        <li>Wpisz 6-cyfrowy kod, który pokaże aplikacja.</li>
      </ol>
      {/* SVG z własnego backendu (segno) – bez danych od użytkownika */}
      <div className="qr" dangerouslySetInnerHTML={{ __html: qr.qr_svg }} />
      <details className="hint">
        <summary>Nie możesz zeskanować? Wpisz klucz ręcznie</summary>
        <code className="sekret">{qr.sekret.match(/.{1,4}/g).join(' ')}</code>
      </details>
      <label className="field">Kod z aplikacji
        <input inputMode="numeric" autoComplete="one-time-code" pattern="[0-9 ]{6,7}" maxLength={7} required
          value={kod} onChange={(e) => setKod(e.target.value)} autoFocus />
      </label>
      {blad && <p className="txt-danger">{blad}</p>}
      <button type="submit" className="btn btn-primary" disabled={trwa}>{trwa ? 'Sprawdzam…' : 'Potwierdź'}</button>
    </form>
  )
}

export function KonfiguracjaKlucza({ onGotowe }) {
  const [nazwa, setNazwa] = useState('Klucz sprzętowy')
  const [blad, setBlad] = useState(null)
  const [trwa, setTrwa] = useState(false)

  if (!kluczeDostepne()) {
    return <p className="hint">Klucze sprzętowe działają tylko przez HTTPS albo na http://localhost. Użyj aplikacji uwierzytelniającej.</p>
  }

  async function rejestruj(e) {
    e.preventDefault()
    setBlad(null)
    setTrwa(true)
    try {
      const credential = await zarejestrujKlucz(await api.kluczRejestracjaOpcje())
      onGotowe(await api.kluczRejestracja(credential, nazwa))
    } catch (err) {
      setBlad(err instanceof DOMException ? bladKlucza(err) : err.message)
    } finally {
      setTrwa(false)
    }
  }

  return (
    <form onSubmit={rejestruj}>
      <p className="hint">YubiKey, SoloKey, Google Titan lub inny klucz FIDO2 / U2F.</p>
      <label className="field">Nazwa klucza
        <input value={nazwa} onChange={(e) => setNazwa(e.target.value)} maxLength={60} required />
      </label>
      {blad && <p className="txt-danger">{blad}</p>}
      <button type="submit" className="btn btn-primary" disabled={trwa}>
        {trwa ? 'Dotknij klucza…' : 'Zarejestruj klucz'}
      </button>
    </form>
  )
}

export default function Konfiguracja2FA({ onGotowe }) {
  const [metoda, setMetoda] = useState('totp')
  return (
    <div>
      <div className="przelacznik" role="tablist">
        <button type="button" role="tab" aria-selected={metoda === 'totp'}
          className={`btn ${metoda === 'totp' ? 'btn-primary' : ''}`} onClick={() => setMetoda('totp')}>
          Aplikacja w telefonie
        </button>
        <button type="button" role="tab" aria-selected={metoda === 'klucz'}
          className={`btn ${metoda === 'klucz' ? 'btn-primary' : ''}`} onClick={() => setMetoda('klucz')}>
          Klucz sprzętowy
        </button>
      </div>
      {metoda === 'totp' ? <KonfiguracjaTotp onGotowe={onGotowe} /> : <KonfiguracjaKlucza onGotowe={onGotowe} />}
    </div>
  )
}
