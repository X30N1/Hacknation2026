import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import AnonimizacjaPodglad from '../components/AnonimizacjaPodglad'
import OcrBaner from '../components/OcrBaner'
import { jakoPlikTxt } from '../lib/anonimizacja'
import { addDays, formatPL, todayISO } from '../lib/dates'
import { METODA } from '../lib/labels'

const AKCEPTOWANE = '.pdf,.docx,.txt'

// Rejestracja wniosku: odczyt (bez zapisu) → anonimizacja + dane sprawy → zapis sprawy i WYŁĄCZNIE
// zanonimizowanej treści. Oryginał nie trafia do bazy.
export default function NowyWniosek() {
  const [etap, setEtap] = useState('plik') // plik | analiza | formularz
  const [blad, setBlad] = useState(null)
  const [odczyt, setOdczyt] = useState(null)
  const [tekst, setTekst] = useState('')
  const [edycjaTekstu, setEdycjaTekstu] = useState(false)
  const [zanonimizowany, setZanonimizowany] = useState(null)
  const [wnioskodawcaOdczyt, setWnioskodawcaOdczyt] = useState('')
  const [dane, setDane] = useState({ znak: '', data_wplywu: todayISO(), wnioskodawca: '', przedmiot: '', inicjaly: '' })
  const [przeciaganie, setPrzeciaganie] = useState(false)
  const [zapis, setZapis] = useState(false)
  const utworzonaSprawa = useRef(null) // przy ponowieniu po błędzie zapisu dokumentu nie twórz sprawy drugi raz
  const input = useRef(null)
  const navigate = useNavigate()

  async function wyslijPlik(plik) {
    if (!plik) return
    setBlad(null)
    setEtap('analiza')
    try {
      const wynik = await api.odczytajWniosek(plik)
      setOdczyt(wynik.odczyt)
      setTekst(wynik.odczyt.tekst)
      setWnioskodawcaOdczyt(wynik.propozycja.wnioskodawca || '')
      setDane((d) => ({ ...d, ...Object.fromEntries(Object.entries(wynik.propozycja).filter(([, v]) => v)) }))
      setEdycjaTekstu(!wynik.odczyt.tekst.trim()) // pusty odczyt (np. pismo odręczne) – od razu do wpisania
      utworzonaSprawa.current = null
      setEtap('formularz')
    } catch (e) {
      setBlad(e.message)
      setEtap('plik')
    }
  }

  async function zatwierdz(e) {
    e.preventDefault()
    if (zanonimizowany == null) return
    setBlad(null)
    setZapis(true)
    try {
      if (!utworzonaSprawa.current) utworzonaSprawa.current = await api.utworzSprawe(dane)
      const sid = utworzonaSprawa.current.id
      await api.dodajDokument(sid, jakoPlikTxt(odczyt.nazwa_pliku, zanonimizowany), 'WNIOSEK')
      navigate(`/sprawy/${sid}`)
    } catch (err) {
      setBlad(utworzonaSprawa.current
        ? `Sprawa ${utworzonaSprawa.current.znak} została utworzona, ale nie zapisano treści wniosku: ${err.message} Spróbuj ponownie.`
        : err.message)
    } finally {
      setZapis(false)
    }
  }

  const pole = (k) => ({ value: dane[k], onChange: (e) => setDane({ ...dane, [k]: e.target.value }) })
  const gotowe = !edycjaTekstu && zanonimizowany != null

  return (
    <section>
      <h1>Zarejestruj wniosek</h1>
      {blad && <div className="card error" role="alert">{blad}</div>}

      {etap !== 'formularz' && (
        <div
          className={`dropzone ${przeciaganie ? 'drag' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setPrzeciaganie(true) }}
          onDragLeave={() => setPrzeciaganie(false)}
          onDrop={(e) => { e.preventDefault(); setPrzeciaganie(false); wyslijPlik(e.dataTransfer.files[0]) }}
          onClick={() => input.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => e.key === 'Enter' && input.current?.click()}
        >
          {etap === 'analiza' ? (
            <p><span className="spinner" aria-hidden="true" /> Odczytuję wniosek… (skany mogą potrwać do minuty)</p>
          ) : (
            <>
              <p className="dz-title">Przeciągnij tutaj plik wniosku</p>
              <p className="muted">lub kliknij, aby wybrać · PDF lub Word (DOCX)</p>
              <p className="hint">Plik zostanie tylko odczytany – do systemu trafi treść po anonimizacji.</p>
            </>
          )}
          <input ref={input} type="file" accept={AKCEPTOWANE} hidden onChange={(e) => wyslijPlik(e.target.files[0])} />
        </div>
      )}

      {etap === 'formularz' && odczyt && (
        <form className="grid-2" onSubmit={zatwierdz}>
          <div className="card">
            <div className="doc-head">
              <h2>Treść wniosku</h2>
              {edycjaTekstu ? (
                <button type="button" className="btn btn-small" disabled={!tekst.trim()} onClick={() => setEdycjaTekstu(false)}>
                  Gotowe – przejdź do anonimizacji
                </button>
              ) : (
                <button type="button" className="btn btn-small" onClick={() => setEdycjaTekstu(true)}>Popraw tekst</button>
              )}
            </div>
            <p className="muted">{odczyt.nazwa_pliku} · {METODA[odczyt.metoda] || odczyt.metoda}</p>
            <OcrBaner dokument={odczyt} />
            {edycjaTekstu ? (
              <>
                <textarea className="doc-text" value={tekst} onChange={(e) => setTekst(e.target.value)} rows={20} aria-label="Treść wniosku" />
                <p className="hint">Po poprawieniu tekstu propozycje anonimizacji zostaną wyszukane od nowa.</p>
              </>
            ) : (
              <AnonimizacjaPodglad tekst={tekst} wnioskodawca={wnioskodawcaOdczyt} onZmiana={setZanonimizowany} />
            )}
          </div>

          <div className="card">
            <h2>Dane sprawy</h2>
            <p className="muted">Uzupełnione automatycznie – sprawdź przed zatwierdzeniem.</p>
            <label className="field">Numer sprawy<input required {...pole('znak')} placeholder="BKS.IV.1431.123.2026" /></label>
            <label className="field">Data wpływu<input type="date" required {...pole('data_wplywu')} /></label>
            <p className="hint">
              Termin ustawowy (14 dni, art. 13 ust. 1 UDIP): <strong>{dane.data_wplywu ? formatPL(addDays(dane.data_wplywu, 14)) : '—'}</strong>
            </p>
            <label className="field">Wnioskodawca<input {...pole('wnioskodawca')} /></label>
            <label className="field">Przedmiot (krótki opis)<textarea rows={3} {...pole('przedmiot')} /></label>
            <label className="field">Inicjały osoby prowadzącej<input {...pole('inicjaly')} maxLength={10} placeholder="np. AK" /></label>
            <div className="actions">
              <button type="button" className="btn" onClick={() => { setEtap('plik'); setOdczyt(null) }}>Wgraj inny plik</button>
              <button type="submit" className="btn btn-primary" disabled={zapis || !gotowe}>
                {zapis ? 'Zapisuję…' : 'Zanonimizuj i dodaj do kalendarza'}
              </button>
            </div>
            {edycjaTekstu && <p className="hint">Zakończ poprawianie tekstu, aby przejść do anonimizacji.</p>}
            {!edycjaTekstu && zanonimizowany == null && (
              <p className="hint">Zaakceptuj anonimizację treści („Akceptuję – pokaż zamazane”), aby zarejestrować wniosek.</p>
            )}
          </div>
        </form>
      )}
    </section>
  )
}
