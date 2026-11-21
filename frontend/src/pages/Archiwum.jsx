import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import NowyDokument from '../components/NowyDokument'
import { formatPL } from '../lib/dates'
import { RODZAJ_DOKUMENTU, RODZAJE_WIEDZY } from '../lib/labels'
import Podswietl from '../components/Podswietl'

const AKCEPTOWANE = '.pdf,.docx,.txt'

function Wyszukiwarka() {
  const [fraza, setFraza] = useState('')
  const [wyniki, setWyniki] = useState(null)
  const [blad, setBlad] = useState(null)
  const [trwa, setTrwa] = useState(false)

  async function szukaj(e) {
    e.preventDefault()
    if (fraza.trim().length < 2) return
    setBlad(null)
    setTrwa(true)
    try {
      setWyniki(await api.szukajWArchiwum(fraza.trim()))
    } catch (err) {
      setBlad(err.message)
    } finally {
      setTrwa(false)
    }
  }

  return (
    <div className="card">
      <h2>Szukaj w archiwum</h2>
      <form className="search" onSubmit={szukaj} role="search">
        <input id="fraza" type="search" value={fraza} onChange={(e) => setFraza(e.target.value)}
          placeholder="np. dotacje dla organizacji, odśnieżanie ulic, art. 13" aria-label="Szukana fraza" />
        <button type="submit" className="btn btn-primary" disabled={trwa || fraza.trim().length < 2}>
          {trwa ? 'Szukam…' : 'Szukaj'}
        </button>
      </form>
      <p className="hint">Przeszukuje sprawy, wnioski, odpowiedzi wydziałów, pisma i bazę wiedzy (zanonimizowane teksty).</p>
      {blad && <p className="txt-danger">{blad}</p>}
      {wyniki?.length === 0 && <p className="muted">Nic nie znaleziono.</p>}
      <ul className="podobne">
        {wyniki?.map((t) => (
          <li key={`${t.rodzaj}-${t.dokument_id ?? t.sprawa_id}`}>
            <div className="podobne-head">
              <span className="pill pill-muted">{RODZAJ_DOKUMENTU[t.rodzaj] || t.rodzaj}</span>
              {t.sprawa_id ? <Link to={`/sprawy/${t.sprawa_id}`}>{t.znak}</Link> : <strong>{t.nazwa_pliku}</strong>}
              {t.sprawa_id && t.nazwa_pliku && <span className="muted">{t.nazwa_pliku}</span>}
              {t.data && <span className="muted">{formatPL(t.data)}</span>}
            </div>
            <div className="fragment"><Podswietl tekst={t.fragment} /></div>
          </li>
        ))}
      </ul>
    </div>
  )
}

function BazaWiedzy() {
  const [lista, setLista] = useState(null)
  const [blad, setBlad] = useState(null)
  const [nowy, setNowy] = useState(null)
  const [doUsuniecia, setDoUsuniecia] = useState(null)
  const input = useRef(null)

  const wczytaj = useCallback(() => api.wiedza().then(setLista).catch((e) => setBlad(e.message)), [])
  useEffect(() => { wczytaj() }, [wczytaj])

  function wybrano(plik) {
    if (input.current) input.current.value = ''
    if (plik) setNowy({ plik, tytul: 'Dodaj do bazy wiedzy', rodzaj: 'USTAWA', rodzaje: RODZAJE_WIEDZY, przycisk: 'Zanonimizuj i dodaj' })
  }

  async function zapisz(plikTxt, { rodzaj }) {
    await api.dodajWiedze(plikTxt, rodzaj)
    setNowy(null)
    await wczytaj()
  }

  async function usun(id) {
    setBlad(null)
    try {
      await api.usunWiedze(id)
      setDoUsuniecia(null)
      await wczytaj()
    } catch (e) {
      setBlad(e.message)
    }
  }

  return (
    <>
      {nowy && <NowyDokument key={nowy.plik.name + nowy.plik.lastModified} zadanie={nowy} onZapisz={zapisz} onAnuluj={() => setNowy(null)} />}
      <div className="card">
        <div className="doc-head">
          <h2>Baza wiedzy</h2>
          <button type="button" className="btn btn-primary" disabled={!!nowy} onClick={() => input.current?.click()}>Dodaj plik</button>
          <input ref={input} type="file" accept={AKCEPTOWANE} hidden onChange={(e) => wybrano(e.target.files[0])} />
        </div>
        <p className="hint">
          Ustawy, zarządzenia, wzory pism i archiwalne odpowiedzi. System korzysta z nich w wyszukiwarce
          i przy przygotowaniu projektów odpowiedzi. Przy zmianie ustawy dodaj nową wersję i usuń starą.
        </p>
        {blad && <p className="txt-danger">{blad}</p>}
        {lista?.length === 0 && <p className="muted">Baza wiedzy jest pusta.</p>}
        {lista?.length > 0 && (
          <div className="table-wrap">
            <table className="cal">
              <thead><tr><th>Plik</th><th>Rodzaj</th><th>Znaki</th><th>Dodano</th><th aria-label="Akcje" /></tr></thead>
              <tbody>
                {lista.map((w) => (
                  <tr key={w.id}>
                    <td>{w.nazwa_pliku}</td>
                    <td>{RODZAJ_DOKUMENTU[w.rodzaj] || w.rodzaj}</td>
                    <td className="nowrap">{w.znaki.toLocaleString('pl-PL')}</td>
                    <td className="nowrap">{formatPL(w.utworzono.slice(0, 10))}</td>
                    <td className="nowrap">
                      {doUsuniecia === w.id ? (
                        <>
                          <span className="hint">Usunąć? </span>
                          <button type="button" className="btn btn-small" onClick={() => usun(w.id)}>Tak, usuń</button>{' '}
                          <button type="button" className="btn btn-small" onClick={() => setDoUsuniecia(null)}>Nie</button>
                        </>
                      ) : (
                        <button type="button" className="btn btn-small" onClick={() => setDoUsuniecia(w.id)}>Usuń</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}

export default function Archiwum() {
  return (
    <section>
      <h1>Archiwum i baza wiedzy</h1>
      <Wyszukiwarka />
      <BazaWiedzy />
    </section>
  )
}
