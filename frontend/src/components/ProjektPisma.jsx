import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import AnonimizacjaPodglad from './AnonimizacjaPodglad'

// Projekt odpowiedzi: system układa pismo z odpowiedzi wydziałów → urzędnik sprawdza i poprawia
// treść → anonimizacja (szare → po akceptacji czarne) → zapis projektu (status „Odpowiedź przygotowana”).
export default function ProjektOdpowiedzi({ sprawa, onZapisz, onAnuluj }) {
  const [projekt, setProjekt] = useState(null)
  const [tekst, setTekst] = useState('')
  const [etap, setEtap] = useState('tresc') // tresc | anonimizacja
  const [zanonimizowany, setZanonimizowany] = useState(null)
  const [blad, setBlad] = useState(null)
  const [zapis, setZapis] = useState(false)
  const panel = useRef(null)

  useEffect(() => {
    let aktualne = true
    panel.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    api.projektOdpowiedzi(sprawa.id)
      .then((p) => { if (aktualne) { setProjekt(p); setTekst(p.tekst) } })
      .catch((e) => aktualne && setBlad(e.message))
    return () => { aktualne = false }
  }, [sprawa.id])

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

  const odpWydzialow = sprawa.dokumenty.filter((d) => d.rodzaj === 'ODP_WYDZIALU').length

  return (
    <div className="card panel" ref={panel}>
      <div className="doc-head">
        <h2>Projekt odpowiedzi</h2>
        <span className="muted">{sprawa.znak} · odpowiedzi wydziałów: {odpWydzialow}</span>
      </div>
      {blad && <div className="card error" role="alert">{blad}</div>}
      {!projekt && !blad && (
        <p className="muted"><span className="spinner" aria-hidden="true" /> Przygotowuję projekt pisma…</p>
      )}
      {projekt && etap === 'tresc' && (
        <>
          <div className="banner banner-info inline-banner">
            To projekt – sprawdź go merytorycznie przed dalszymi krokami. Pola [DO UZUPEŁNIENIA] wymagają Twojej decyzji.
            {projekt.llm_uzyty ? ' Treść ułożył model AI na podstawie wgranych dokumentów.' : ' Projekt z szablonu pisma.'}
          </div>
          {projekt.uwagi.map((u) => <p key={u} className="hint txt-danger">{u}</p>)}
          <textarea className="doc-text" rows={22} value={tekst} onChange={(e) => setTekst(e.target.value)} aria-label="Treść projektu odpowiedzi" />
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
      <div className="actions">
        <button type="button" className="btn" disabled={zapis} onClick={onAnuluj}>Anuluj</button>
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
            {zapis ? 'Zapisuję…' : 'Zatwierdź projekt odpowiedzi'}
          </button>
        )}
      </div>
    </div>
  )
}
