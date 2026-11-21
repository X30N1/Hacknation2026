import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import { KATEGORIE, ZASLONA, wykryj, zamaz } from '../lib/anonimizacja'

// Przesunięcie zaznaczenia (Selection) w całym tekście dokumentu: każdy <span data-s> ma jeden węzeł tekstowy.
function przesuniecie(wezel, offset) {
  const el = (wezel.nodeType === 3 ? wezel.parentElement : wezel)?.closest('[data-s]')
  return el ? Number(el.dataset.s) + (wezel.nodeType === 3 ? offset : 0) : null
}

// Krok anonimizacji PRZED zapisem dokumentu. Etap 1: dane do zamazania na szaro – klik w szary
// fragment = nie zamazuj, zaznaczenie myszą + „Zamaż zaznaczony tekst” = dodaj ręcznie.
// Etap 2 (po akceptacji urzędnika): te same dane na czarno – dokładnie to, co zostanie zapisane.
// Rodzic dostaje przez onZmiana gotowy tekst zanonimizowany (null przed akceptacją)
// i to on – a nie oryginał – trafia do bazy.
export default function AnonimizacjaPodglad({ tekst, wnioskodawca, onZmiana }) {
  const [fragmenty, setFragmenty] = useState([])
  const [laduje, setLaduje] = useState(true)
  const [uwagi, setUwagi] = useState([])
  const [komunikat, setKomunikat] = useState('')
  const [czarne, setCzarne] = useState(false)
  const kontener = useRef(null)
  const nextId = useRef(0)

  // Propozycje z backendu (wzorce + wnioskodawca + model językowy); bez backendu – lokalne wzorce.
  useEffect(() => {
    let aktualne = true
    const ustaw = (lista, uw) => {
      if (!aktualne) return
      setFragmenty(lista.map((f, i) => ({ ...f, id: i, wybrany: true })))
      nextId.current = lista.length
      setUwagi(uw)
      setLaduje(false)
    }
    api.anonimizacjaTekstu(tekst, wnioskodawca || null)
      .then((r) => ustaw(r.fragmenty, r.uwagi || []))
      .catch(() => ustaw(wykryj(tekst), ['Brak połączenia z serwerem – propozycje tylko z prostych wzorców.']))
    return () => { aktualne = false }
  }, [tekst, wnioskodawca])

  const wybrane = fragmenty.filter((f) => f.wybrany)

  // Rodzic dostaje tekst do zapisu dopiero po akceptacji (etap 2) – wcześniej null = zapis zablokowany.
  useEffect(() => {
    onZmiana(laduje || !czarne ? null : zamaz(tekst, fragmenty.filter((f) => f.wybrany)))
  }, [fragmenty, laduje, czarne, tekst, onZmiana])

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

  // Etap 2: po akceptacji zaznaczenia – dokument tak, jak zostanie zapisany (zamazane na czarno).
  if (czarne) {
    return (
      <div className="anon">
        <div className="anon-head">
          <strong>Wersja po anonimizacji</strong>
          <span className="muted">zamazano: {wybrane.length}</span>
          <button type="button" className="btn btn-small" onClick={() => setCzarne(false)}>Wróć do zaznaczania</button>
        </div>
        <p className="hint">Tak dokument trafi do systemu. Czarne pola zastąpią dane – oryginału nie da się z nich odtworzyć.</p>
        <pre className="doc-text readonly anon-text">
          {segmenty.map((s) => (s.f?.wybrany
            ? <span key={s.f.id} className="redacted" title={s.f.etykieta || KATEGORIE[s.f.kategoria]}>{ZASLONA}</span>
            : <span key={`t${s.start}`}>{s.tekst}</span>))}
        </pre>
      </div>
    )
  }

  return (
    <div className="anon">
      <div className="anon-head">
        <strong>Anonimizacja przed zapisem</strong>
        <span className="muted">do zamazania: {wybrane.length} z {fragmenty.length}</span>
        <button type="button" className="btn btn-small btn-primary" disabled={laduje} onClick={() => setCzarne(true)}>
          Akceptuję – pokaż zamazane
        </button>
      </div>
      <p className="hint">
        Do systemu trafi tylko ta wersja – szare fragmenty zostaną zamazane (klik = nie zamazuj). Danych, których
        system nie wykrył, zaznacz myszą i użyj „Zamaż zaznaczony tekst”.
      </p>
      {laduje && <p className="muted"><span className="spinner" aria-hidden="true" /> Wyszukuję dane do zamazania…</p>}
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
    </div>
  )
}
