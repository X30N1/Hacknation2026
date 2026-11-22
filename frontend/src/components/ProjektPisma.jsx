import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import AnonimizacjaPodglad from './AnonimizacjaPodglad'

// Projekt pisma (draft AI): system układa pismo z dokumentów sprawy i bazy wiedzy (można anulować
// w trakcie generacji) → urzędnik sprawdza i poprawia treść → anonimizacja (szare → po akceptacji
// czarne) → zapis dokumentu i zdarzenia w historii.
// zadanie = { tytul, rodzaj: ODPOWIEDZ | WEZWANIE | PRZEKAZANIE | PRZEDLUZENIE, wydzialy?, nowy_termin?, przycisk }
export default function ProjektPisma({ sprawa, zadanie, onZapisz, onAnuluj }) {
  const [projekt, setProjekt] = useState(null)
  const [tekst, setTekst] = useState('')
  const [etap, setEtap] = useState('tresc') // tresc | anonimizacja
  const [zanonimizowany, setZanonimizowany] = useState(null)
  const [blad, setBlad] = useState(null)
  const [zapis, setZapis] = useState(false)
  const panel = useRef(null)
  const przerwij = useRef(null)
  const { rodzaj, wydzialy, nowy_termin: nowyTermin } = zadanie

  useEffect(() => {
    const ctrl = new AbortController()
    przerwij.current = ctrl
    panel.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    api.draftPisma(sprawa.id, { rodzaj, wydzialy: wydzialy || [], nowy_termin: nowyTermin || null }, ctrl.signal)
      .then((p) => { setProjekt(p); setTekst(p.tekst) })
      .catch((e) => e?.name !== 'AbortError' && setBlad(e.message))
    return () => ctrl.abort() // zamknięcie panelu / zmiana sprawy przerywa generację na serwerze
  }, [sprawa.id, rodzaj, wydzialy, nowyTermin])

  function anuluj() {
    przerwij.current?.abort()
    onAnuluj()
  }

  async function zapisz() {
    if (zanonimizowany == null) return
    setBlad(null)
    setZapis(true)
    try {
      await onZapisz(zanonimizowany)
    } catch (e) {
      setBlad(e.message)
      setZapis(false)
    }
  }

  const generuje = !projekt && !blad

  return (
    <div className="card panel" ref={panel}>
      <div className="doc-head">
        <h2>{zadanie.tytul} – draft AI</h2>
        <span className="muted">{sprawa.znak}</span>
      </div>
      {blad && <div className="card error" role="alert">{blad}</div>}
      {generuje && (
        <div className="czekanie" role="status" aria-live="polite">
          <p><span className="spinner" aria-hidden="true" /> Przygotowuję projekt pisma na podstawie dokumentów sprawy i bazy wiedzy…</p>
          <p className="hint">Lokalny model może potrzebować kilku minut.</p>
          <button type="button" className="btn" onClick={anuluj}>Anuluj</button>
        </div>
      )}
      {projekt && etap === 'tresc' && (
        <>
          <div className="banner banner-info inline-banner">
            To projekt – sprawdź go merytorycznie przed dalszymi krokami. Pola [DO UZUPEŁNIENIA] wymagają Twojej decyzji.
            {projekt.llm_uzyty ? ' Treść ułożył model AI na podstawie dokumentów sprawy i bazy wiedzy.' : ' Projekt z szablonu pisma.'}
          </div>
          {projekt.uwagi.map((u) => <p key={u} className="hint txt-danger">{u}</p>)}
          <textarea className="doc-text" rows={22} value={tekst} onChange={(e) => setTekst(e.target.value)} aria-label="Treść projektu pisma" />
          {projekt.zrodla.length > 0 && (
            <details className="zrodla">
              <summary>Na podstawie ({projekt.zrodla.length})</summary>
              <ul>{projekt.zrodla.map((z) => <li key={z}>{z}</li>)}</ul>
            </details>
          )}
        </>
      )}
      {projekt && etap === 'anonimizacja' && (
        <AnonimizacjaPodglad tekst={tekst} wnioskodawca={sprawa.wnioskodawca} onZmiana={setZanonimizowany} />
      )}
      {!generuje && (
        <div className="actions">
          <button type="button" className="btn" disabled={zapis} onClick={anuluj}>Anuluj</button>
          {etap === 'anonimizacja' && (
            <button type="button" className="btn" disabled={zapis} onClick={() => { setEtap('tresc'); setZanonimizowany(null) }}>
              Wróć do treści
            </button>
          )}
          {etap === 'tresc' ? (
            <button type="button" className="btn btn-primary" disabled={!projekt || !tekst.trim()} onClick={() => setEtap('anonimizacja')}>
              Treść sprawdzona – przejdź do anonimizacji
            </button>
          ) : (
            <button type="button" className="btn btn-primary" disabled={zapis || zanonimizowany == null} onClick={zapisz}>
              {zapis ? 'Zapisuję…' : zadanie.przycisk}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
