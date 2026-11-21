import { useState } from 'react'
import { api } from '../api/client'

export default function ZmianaHasla({ minDlugosc = 10, onGotowe, przycisk = 'Zmień hasło' }) {
  const [stare, setStare] = useState('')
  const [nowe, setNowe] = useState('')
  const [powtorz, setPowtorz] = useState('')
  const [blad, setBlad] = useState(null)
  const [trwa, setTrwa] = useState(false)

  async function wyslij(e) {
    e.preventDefault()
    setBlad(null)
    if (nowe !== powtorz) return setBlad('Hasła nie są takie same.')
    setTrwa(true)
    try {
      onGotowe(await api.zmienHaslo(stare, nowe))
      setStare(''); setNowe(''); setPowtorz('')
    } catch (err) {
      setBlad(err.message)
    } finally {
      setTrwa(false)
    }
  }

  return (
    <form onSubmit={wyslij}>
      <label className="field">Obecne hasło
        <input type="password" autoComplete="current-password" required value={stare} onChange={(e) => setStare(e.target.value)} />
      </label>
      <label className="field">Nowe hasło (min. {minDlugosc} znaków)
        <input type="password" autoComplete="new-password" required minLength={minDlugosc} value={nowe}
          onChange={(e) => setNowe(e.target.value)} />
      </label>
      <label className="field">Powtórz nowe hasło
        <input type="password" autoComplete="new-password" required minLength={minDlugosc} value={powtorz}
          onChange={(e) => setPowtorz(e.target.value)} />
      </label>
      {blad && <p className="txt-danger">{blad}</p>}
      <button type="submit" className="btn btn-primary" disabled={trwa}>{trwa ? 'Zapisuję…' : przycisk}</button>
    </form>
  )
}
