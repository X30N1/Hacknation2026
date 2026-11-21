import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import OcrBaner from '../components/OcrBaner'
import { addDays, formatPL, todayISO } from '../lib/dates'
import { METODA } from '../lib/labels'

const AKCEPTOWANE = '.pdf,.docx,.txt'

export default function NowyWniosek() {
  const [etap, setEtap] = useState('plik') // plik | analiza | formularz
  const [blad, setBlad] = useState(null)
  const [dokument, setDokument] = useState(null)
  const [tekst, setTekst] = useState('')
  const [dane, setDane] = useState({ znak: '', data_wplywu: todayISO(), wnioskodawca: '', przedmiot: '', inicjaly: '' })
  const [przeciaganie, setPrzeciaganie] = useState(false)
  const [zapis, setZapis] = useState(false)
  const input = useRef(null)
  const navigate = useNavigate()

  async function wyslijPlik(plik) {
    if (!plik) return
    setBlad(null)
    setEtap('analiza')
    try {
      const wynik = await api.analizujWniosek(plik)
      setDokument(wynik.dokument)
      setTekst(wynik.dokument.tekst)
      setDane((d) => ({ ...d, ...Object.fromEntries(Object.entries(wynik.propozycja).filter(([, v]) => v)) }))
      setEtap('formularz')
    } catch (e) {
      setBlad(e.message)
      setEtap('plik')
    }
  }

  async function zatwierdz(e) {
    e.preventDefault()
    setBlad(null)
    setZapis(true)
    try {
      if (tekst !== dokument.tekst) await api.poprawTekst(dokument.id, tekst)
      const sprawa = await api.utworzSprawe({ ...dane, dokument_id: dokument.id })
      navigate(`/sprawy/${sprawa.id}`)
    } catch (err) {
      setBlad(err.message)
    } finally {
      setZapis(false)
    }
  }

  const pole = (k) => ({ value: dane[k], onChange: (e) => setDane({ ...dane, [k]: e.target.value }) })

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
            </>
          )}
          <input ref={input} type="file" accept={AKCEPTOWANE} hidden onChange={(e) => wyslijPlik(e.target.files[0])} />
        </div>
      )}

      {etap === 'formularz' && dokument && (
        <form className="grid-2" onSubmit={zatwierdz}>
          <div className="card">
            <h2>Treść wniosku</h2>
            <p className="muted">
              {dokument.nazwa_pliku} · {METODA[dokument.metoda] || dokument.metoda}
            </p>
            <OcrBaner dokument={dokument} />
            <textarea className="doc-text" value={tekst} onChange={(e) => setTekst(e.target.value)} rows={20} aria-label="Treść wniosku" />
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
              <button type="button" className="btn" onClick={() => { setEtap('plik'); setDokument(null) }}>Wgraj inny plik</button>
              <button type="submit" className="btn btn-primary" disabled={zapis}>{zapis ? 'Zapisuję…' : 'Zatwierdź i dodaj do kalendarza'}</button>
            </div>
          </div>
        </form>
      )}
    </section>
  )
}
