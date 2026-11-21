import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { jakoPlikTxt } from '../lib/anonimizacja'
import { RODZAJ_DOKUMENTU } from '../lib/labels'
import AnonimizacjaPodglad from './AnonimizacjaPodglad'
import OcrBaner from './OcrBaner'

// Dodawanie dokumentu: odczyt BEZ zapisu → (poprawa tekstu) → anonimizacja (szare → czarne)
// → zapis wyłącznie zanonimizowanej treści. Oryginał nie trafia do bazy.
// zadanie = { plik, tytul, przycisk, rodzaj, rodzaje?: string[], wydzialy?: {skrot,nazwa}[], wydzial? }
export default function NowyDokument({ zadanie, wnioskodawca, onZapisz, onAnuluj }) {
  const [odczyt, setOdczyt] = useState(null)
  const [tekst, setTekst] = useState('')
  const [edycja, setEdycja] = useState(false)
  const [rodzaj, setRodzaj] = useState(zadanie.rodzaj)
  const [wydzial, setWydzial] = useState(zadanie.wydzial || '')
  const [zanonimizowany, setZanonimizowany] = useState(null)
  const [blad, setBlad] = useState(null)
  const [zapis, setZapis] = useState(false)
  const panel = useRef(null)

  useEffect(() => {
    let aktualne = true
    panel.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    api.odczytajDokument(zadanie.plik)
      .then((o) => {
        if (!aktualne) return
        setOdczyt(o)
        setTekst(o.tekst)
        setEdycja(!o.tekst.trim()) // pusty odczyt (np. pismo odręczne) – od razu do wpisania
      })
      .catch((e) => aktualne && setBlad(e.message))
    return () => { aktualne = false }
  }, [zadanie])

  const brakWydzialu = zadanie.wydzialy && !wydzial

  async function zapisz() {
    if (zanonimizowany == null || brakWydzialu) return
    setBlad(null)
    setZapis(true)
    try {
      await onZapisz(jakoPlikTxt(odczyt.nazwa_pliku, zanonimizowany), { rodzaj, wydzial: wydzial || null })
    } catch (e) {
      setBlad(e.message)
      setZapis(false)
    }
  }

  return (
    <div className="card panel" ref={panel}>
      <div className="doc-head">
        <h2>{zadanie.tytul}</h2>
        <span className="muted">{zadanie.plik.name}</span>
      </div>
      {blad && <div className="card error" role="alert">{blad}</div>}
      {!odczyt && !blad && (
        <p className="muted"><span className="spinner" aria-hidden="true" /> Odczytuję dokument… (skany rozpoznawane przez OCR mogą potrwać kilka minut)</p>
      )}
      {odczyt && (
        <>
          <OcrBaner dokument={odczyt} />
          <div className="actions anon-toolbar">
            {zadanie.rodzaje && (
              <label className="field inline">Rodzaj
                <select value={rodzaj} onChange={(e) => setRodzaj(e.target.value)}>
                  {zadanie.rodzaje.map((r) => <option key={r} value={r}>{RODZAJ_DOKUMENTU[r] || r}</option>)}
                </select>
              </label>
            )}
            {zadanie.wydzialy && (
              <label className="field inline">Wydział, który odpowiedział
                <select value={wydzial} onChange={(e) => setWydzial(e.target.value)} required>
                  <option value="">— wybierz —</option>
                  {zadanie.wydzialy.map((w) => <option key={w.skrot} value={w.skrot}>{w.skrot} – {w.nazwa}</option>)}
                </select>
              </label>
            )}
            {edycja ? (
              <button type="button" className="btn btn-small" disabled={!tekst.trim()} onClick={() => setEdycja(false)}>
                Gotowe – przejdź do anonimizacji
              </button>
            ) : (
              <button type="button" className="btn btn-small" onClick={() => setEdycja(true)}>Popraw tekst</button>
            )}
          </div>
          {edycja ? (
            <textarea className="doc-text" rows={16} value={tekst} onChange={(e) => setTekst(e.target.value)} aria-label="Treść dokumentu" />
          ) : (
            <AnonimizacjaPodglad tekst={tekst} wnioskodawca={wnioskodawca} onZmiana={setZanonimizowany} />
          )}
        </>
      )}
      <div className="actions">
        {zanonimizowany == null && odczyt && !edycja && (
          <span className="hint">Zaakceptuj anonimizację („Akceptuję – pokaż zamazane”), aby zapisać.</span>
        )}
        {brakWydzialu && <span className="hint txt-danger">Wybierz wydział.</span>}
        <button type="button" className="btn" disabled={zapis} onClick={onAnuluj}>Anuluj</button>
        <button type="button" className="btn btn-primary" disabled={zapis || edycja || zanonimizowany == null || brakWydzialu} onClick={zapisz}>
          {zapis ? 'Zapisuję…' : zadanie.przycisk}
        </button>
      </div>
    </div>
  )
}
