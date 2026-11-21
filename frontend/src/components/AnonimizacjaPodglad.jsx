import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import { KATEGORIE, ZASLONA, wykryj, zamaz } from '../lib/anonimizacja'

// Przesunięcie zaznaczenia (Selection) w całym tekście dokumentu: każdy <span data-s> ma jeden węzeł tekstowy.
function przesuniecie(wezel, offset) {
  const el = (wezel.nodeType === 3 ? wezel.parentElement : wezel)?.closest('[data-s]')
  return el ? Number(el.dataset.s) + (wezel.nodeType === 3 ? offset : 0) : null
}

function pobierz(nazwa, tekst) {
  const url = URL.createObjectURL(new Blob([tekst], { type: 'text/plain;charset=utf-8' }))
  const a = Object.assign(document.createElement('a'), { href: url, download: nazwa })
  a.click()
  URL.revokeObjectURL(url)
}

// Podgląd dokumentu z wykrytymi danymi zaznaczonymi na szaro. Klik w szary fragment = nie zamazuj,
// zaznaczenie zwykłego tekstu myszą + „Zamaż zaznaczony tekst” = dodaj ręcznie.
export default function AnonimizacjaPodglad({ dokument, onZamknij }) {
  const tekst = dokument.tekst
  const [fragmenty, setFragmenty] = useState([])
  const [laduje, setLaduje] = useState(true)
  const [uwagi, setUwagi] = useState([])
  const [wynik, setWynik] = useState(null)
  const [komunikat, setKomunikat] = useState('')
  const kontener = useRef(null)
  const nextId = useRef(0)

  // Propozycje z backendu (wzorce + wnioskodawca sprawy + model językowy); bez backendu – lokalne wzorce.
  useEffect(() => {
    let aktualne = true
    const ustaw = (lista, uw) => {
      if (!aktualne) return
      setFragmenty(lista.map((f, i) => ({ ...f, id: i, wybrany: true })))
      nextId.current = lista.length
      setUwagi(uw)
      setLaduje(false)
    }
    api.anonimizacjaDokumentu(dokument.id)
      .then((r) => ustaw(r.fragmenty, r.uwagi || []))
      .catch(() => ustaw(wykryj(tekst), ['Brak połączenia z serwerem – propozycje tylko z prostych wzorców.']))
    return () => { aktualne = false }
  }, [dokument.id, tekst])

  const wybrane = fragmenty.filter((f) => f.wybrany)

  const segmenty = useMemo(() => {
    const out = []
    let poz = 0
    for (const f of [...fragmenty].sort((a, b) => a.start - b.start)) {
      if (f.start > poz) out.push({ start: poz, tekst: tekst.slice(poz, f.start) })
      out.push({ start: f.start, tekst: tekst.slice(f.start, f.end), f })
      poz = f.end
    }
    if (poz < tekst.length) out.push({ start: poz, tekst: tekst.slice(poz) })
    return out
  }, [fragmenty, tekst])

  function przelacz(f) {
    setFragmenty((lista) => (f.kategoria === 'RECZNIE'
      ? lista.filter((x) => x.id !== f.id)
      : lista.map((x) => (x.id === f.id ? { ...x, wybrany: !x.wybrany } : x))))
  }

  function dodajZaznaczony() {
    const sel = window.getSelection()
    if (!sel || sel.isCollapsed || !kontener.current?.contains(sel.anchorNode) || !kontener.current.contains(sel.focusNode)) {
      setKomunikat('Najpierw zaznacz myszą fragment tekstu w podglądzie.')
      return
    }
    const a = przesuniecie(sel.anchorNode, sel.anchorOffset)
    const b = przesuniecie(sel.focusNode, sel.focusOffset)
    if (a == null || b == null) return
    let start = Math.min(a, b)
    let end = Math.max(a, b)
    // obetnij białe znaki na brzegach zaznaczenia
    while (start < end && /\s/.test(tekst[start])) start++
    while (end > start && /\s/.test(tekst[end - 1])) end--
    if (end <= start) return
    setKomunikat('')
    setFragmenty((lista) => [
      ...lista.filter((x) => x.end <= start || x.start >= end), // nowe zaznaczenie zastępuje nakładające się
      { id: nextId.current++, start, end, kategoria: 'RECZNIE', tekst: tekst.slice(start, end), wybrany: true },
    ])
    sel.removeAllRanges()
  }

  const ustawWszystkie = (wybrany) => setFragmenty((l) => l.map((f) => ({ ...f, wybrany })))
  const zamazano = () => setWynik(zamaz(tekst, wybrane))
  const nazwaWyniku = dokument.nazwa_pliku.replace(/\.[^.]+$/, '') + ' (zanonimizowany).txt'

  if (wynik !== null) {
    return (
      <div className="anon">
        <div className="anon-head">
          <strong>Wersja zanonimizowana · zamazano {wybrane.length}</strong>
        </div>
        <pre className="doc-text readonly anon-text">
          {wynik.split(ZASLONA).map((czesc, i, arr) => (
            <span key={i}>{czesc}{i < arr.length - 1 && <span className="redacted" aria-label="zamazane">{ZASLONA}</span>}</span>
          ))}
        </pre>
        <p className="hint">Wersja nie jest zapisywana w aplikacji – pobierz ją lub skopiuj przed zamknięciem.</p>
        <div className="actions">
          <button type="button" className="btn" onClick={() => setWynik(null)}>Wróć do wyboru</button>
          <button type="button" className="btn" onClick={() => navigator.clipboard?.writeText(wynik)}>Kopiuj tekst</button>
          <button type="button" className="btn btn-primary" onClick={() => pobierz(nazwaWyniku, wynik)}>Pobierz .txt</button>
          <button type="button" className="btn" onClick={onZamknij}>Zamknij</button>
        </div>
      </div>
    )
  }

  return (
    <div className="anon">
      <div className="anon-head">
        <strong>Anonimizacja: {dokument.nazwa_pliku}</strong>
        <span className="muted">do zamazania: {wybrane.length} z {fragmenty.length}</span>
      </div>
      <p className="hint">
        Szare fragmenty to dane, które system proponuje zamazać (klik = nie zamazuj). Imion, nazwisk i danych
        wrażliwych system nie rozpozna w całości – zaznacz je myszą i użyj „Zamaż zaznaczony tekst”.
      </p>
      {laduje && <p className="muted">Wyszukuję dane do zamazania…</p>}
      {uwagi.map((u) => <p key={u} className="hint txt-danger">{u}</p>)}
      <div className="actions anon-toolbar">
        <button type="button" className="btn btn-small" onClick={() => ustawWszystkie(true)}>Zaznacz wszystkie</button>
        <button type="button" className="btn btn-small" onClick={() => ustawWszystkie(false)}>Odznacz wszystkie</button>
        <button type="button" className="btn btn-small" onMouseDown={(e) => e.preventDefault()} onClick={dodajZaznaczony}>
          Zamaż zaznaczony tekst
        </button>
        {komunikat && <span className="txt-danger">{komunikat}</span>}
      </div>
      <pre className="doc-text readonly anon-text" ref={kontener}>
        {segmenty.map((s) => (s.f ? (
          <span
            key={s.f.id}
            data-s={s.start}
            role="button"
            tabIndex={0}
            className={`anon-frag ${s.f.wybrany ? 'on' : 'off'}`}
            title={`${s.f.etykieta || KATEGORIE[s.f.kategoria] || s.f.kategoria}${s.f.powod ? ` (${s.f.powod})` : ''} – kliknij, aby ${s.f.kategoria === 'RECZNIE' ? 'usunąć zaznaczenie' : s.f.wybrany ? 'nie zamazywać' : 'zamazać'}`}
            onClick={() => przelacz(s.f)}
            onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), przelacz(s.f))}
          >{s.tekst}</span>
        ) : (
          <span key={`t${s.start}`} data-s={s.start}>{s.tekst}</span>
        )))}
      </pre>
      <div className="actions">
        <button type="button" className="btn" onClick={onZamknij}>Pomiń anonimizację</button>
        <button type="button" className="btn btn-primary" disabled={laduje} onClick={zamazano}>Zamaż wybrane ({wybrane.length})</button>
      </div>
    </div>
  )
}
