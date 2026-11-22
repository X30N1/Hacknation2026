// Panel administratora: ustawienia bezpieczeństwa, dodawanie / usuwanie kont, hasła tymczasowe,
// reset drugiego składnika.
import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { formatPL } from '../lib/dates'

function NowyUzytkownik({ minDlugosc, onDodano }) {
  const [login, setLogin] = useState('')
  const [haslo, setHaslo] = useState('')
  const [rola, setRola] = useState('urzednik')
  const [blad, setBlad] = useState(null)

  async function wyslij(e) {
    e.preventDefault()
    setBlad(null)
    try {
      const u = await api.dodajUzytkownika({ login, haslo, rola })
      setLogin(''); setHaslo(''); setRola('urzednik')
      onDodano(u)
    } catch (err) {
      setBlad(err.message)
    }
  }

  return (
    <form className="card" onSubmit={wyslij}>
      <h2>Nowy użytkownik</h2>
      <div className="form-row">
        <label className="field">Login
          <input required value={login} onChange={(e) => setLogin(e.target.value)} placeholder="np. anna.nowak"
            pattern="[A-Za-z0-9][A-Za-z0-9._\-]{2,39}" autoComplete="off" />
        </label>
        <label className="field">Hasło tymczasowe{minDlugosc > 0 && ` (min. ${minDlugosc} znaków)`}
          <input required minLength={minDlugosc} value={haslo} onChange={(e) => setHaslo(e.target.value)} autoComplete="new-password" />
        </label>
        <label className="field">Rola
          <select value={rola} onChange={(e) => setRola(e.target.value)}>
            <option value="urzednik">Urzędnik</option>
            <option value="admin">Administrator</option>
          </select>
        </label>
      </div>
      <p className="hint">Przekaż hasło użytkownikowi osobiście. Przy pierwszym logowaniu ustawi własne hasło
        (i drugi składnik, jeśli jest wymagany).</p>
      {blad && <p className="txt-danger" role="alert">{blad}</p>}
      <button type="submit" className="btn btn-primary">Dodaj</button>
    </form>
  )
}

function UstawieniaBezpieczenstwa({ onZapisano }) {
  const [dane, setDane] = useState(null)
  const [blad, setBlad] = useState(null)
  const [trwa, setTrwa] = useState(false)

  useEffect(() => { api.bezpieczenstwo().then(setDane).catch((e) => setBlad(e.message)) }, [])

  async function wyslij(e) {
    e.preventDefault()
    setBlad(null)
    setTrwa(true)
    try {
      const zapisane = await api.zapiszBezpieczenstwo(dane)
      setDane(zapisane)
      await onZapisano(zapisane)
    } catch (err) {
      setBlad(err.message)
    } finally {
      setTrwa(false)
    }
  }

  if (!dane) return blad ? <p className="txt-danger" role="alert">{blad}</p> : null

  return (
    <form className="card" onSubmit={wyslij}>
      <h2>Ustawienia bezpieczeństwa</h2>
      <label className="field">
        <span>
          <input type="checkbox" checked={dane.wymagaj_2fa}
            onChange={(e) => setDane({ ...dane, wymagaj_2fa: e.target.checked })} />{' '}
          Wymagaj drugiego składnika (aplikacja uwierzytelniająca albo klucz sprzętowy)
        </span>
      </label>
      <p className="hint">Po włączeniu konta bez drugiego składnika – także Twoje – muszą go skonfigurować przy najbliższej akcji.</p>
      <label className="field">Minimalna długość hasła (0 = bez wymogu)
        <input type="number" min={0} max={128} required value={dane.min_dlugosc_hasla}
          onChange={(e) => setDane({ ...dane, min_dlugosc_hasla: Number(e.target.value) })} />
      </label>
      <p className="hint">Dotyczy nowych haseł – obecne hasła pozostają ważne.</p>
      {blad && <p className="txt-danger" role="alert">{blad}</p>}
      <button type="submit" className="btn btn-primary" disabled={trwa}>{trwa ? 'Zapisuję…' : 'Zapisz ustawienia'}</button>
    </form>
  )
}

function ZmienHaslo({ u, minDlugosc, onGotowe, onAnuluj }) {
  const [haslo, setHaslo] = useState('')
  const [blad, setBlad] = useState(null)

  async function wyslij(e) {
    e.preventDefault()
    setBlad(null)
    try {
      onGotowe(await api.ustawHaslo(u.id, haslo), `Ustawiono hasło tymczasowe dla ${u.login}.`)
    } catch (err) {
      setBlad(err.message)
    }
  }

  return (
    <form className="action-form" onSubmit={wyslij}>
      <label className="field">Nowe hasło tymczasowe dla {u.login}
        <input required minLength={minDlugosc} value={haslo} onChange={(e) => setHaslo(e.target.value)} autoComplete="new-password" autoFocus />
      </label>
      <p className="hint">Użytkownik zostanie wylogowany i przy logowaniu musi zmienić hasło. Konto zostanie odblokowane.</p>
      {blad && <p className="txt-danger">{blad}</p>}
      <div className="action-buttons">
        <button type="submit" className="btn btn-primary btn-small">Ustaw hasło</button>
        <button type="button" className="btn btn-small" onClick={onAnuluj}>Anuluj</button>
      </div>
    </form>
  )
}

export default function Uzytkownicy({ ja, onZmiana }) {
  const [lista, setLista] = useState(null)
  const [blad, setBlad] = useState(null)
  const [info, setInfo] = useState(null)
  const [hasloDla, setHasloDla] = useState(null)

  const odswiez = useCallback(() => api.uzytkownicy().then(setLista).catch((e) => setBlad(e.message)), [])
  useEffect(() => { odswiez() }, [odswiez])

  async function akcja(fn, komunikat) {
    setBlad(null)
    setInfo(null)
    try {
      await fn()
      setInfo(komunikat)
      await odswiez()
    } catch (err) {
      setBlad(err.message)
    }
  }

  const ty = lista?.find((u) => u.login === ja.login)

  return (
    <section>
      <div className="page-head"><h1>Użytkownicy</h1></div>
      {info && <p className="banner-info inline-banner" role="status">{info}</p>}
      {blad && <p className="txt-danger" role="alert">{blad}</p>}

      <UstawieniaBezpieczenstwa onZapisano={async () => {
        setInfo('Zapisano ustawienia bezpieczeństwa.')
        onZmiana(await api.ja())  // np. po włączeniu 2FA administrator bez drugiego składnika musi go dodać
      }} />

      <NowyUzytkownik minDlugosc={ja.min_dlugosc_hasla} onDodano={(u) => { setInfo(`Dodano użytkownika ${u.login}.`); odswiez() }} />

      <div className="table-wrap">
        <table className="cal">
          <thead>
            <tr><th>Login</th><th>Rola</th><th>Drugi składnik</th><th>Stan</th><th>Utworzono</th><th>Akcje</th></tr>
          </thead>
          <tbody>
            {lista?.map((u) => (
              <tr key={u.id}>
                <td><strong>{u.login}</strong>{u.id === ty?.id && <span className="muted"> (Ty)</span>}</td>
                <td>{u.rola === 'admin' ? 'Administrator' : 'Urzędnik'}</td>
                <td>
                  {u.totp && <span className="pill pill-ok">Aplikacja</span>}{' '}
                  {u.klucze > 0 && <span className="pill pill-ok">Klucze: {u.klucze}</span>}
                  {!u.totp && !u.klucze && <span className="pill pill-muted">Brak</span>}
                </td>
                <td>
                  {u.zablokowany_do && <span className="txt-danger">Zablokowane do {u.zablokowany_do.slice(11, 16)}</span>}
                  {!u.zablokowany_do && u.musi_zmienic_haslo && <span className="muted">Czeka na zmianę hasła</span>}
                  {!u.zablokowany_do && !u.musi_zmienic_haslo && 'Aktywne'}
                </td>
                <td className="nowrap">{formatPL(u.utworzono.slice(0, 10))}</td>
                <td>
                  {hasloDla === u.id ? (
                    <ZmienHaslo u={u} minDlugosc={ja.min_dlugosc_hasla} onAnuluj={() => setHasloDla(null)}
                      onGotowe={(_, komunikat) => { setHasloDla(null); setInfo(komunikat); odswiez() }} />
                  ) : (
                    <div className="action-buttons">
                      <button type="button" className="btn btn-small" onClick={() => setHasloDla(u.id)}>
                        {u.zablokowany_do ? 'Odblokuj / ustaw hasło' : 'Ustaw hasło'}
                      </button>
                      {u.id !== ty?.id && (u.totp || u.klucze > 0) && (
                        <button type="button" className="btn btn-small" onClick={() =>
                          window.confirm(`Zresetować drugi składnik użytkownika ${u.login}? Przy logowaniu skonfiguruje go od nowa.`)
                          && akcja(() => api.resetuj2fa(u.id), `Zresetowano drugi składnik użytkownika ${u.login}.`)}>
                          Resetuj 2FA
                        </button>
                      )}
                      {u.id !== ty?.id && (
                        <button type="button" className="btn btn-small btn-danger" onClick={() =>
                          window.confirm(`Usunąć konto ${u.login}? Tej operacji nie można cofnąć.`)
                          && akcja(() => api.usunUzytkownika(u.id), `Usunięto użytkownika ${u.login}.`)}>
                          Usuń
                        </button>
                      )}
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
