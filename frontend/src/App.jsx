import { useEffect, useState } from 'react'
import { Link, NavLink, Route, Routes, useNavigate } from 'react-router-dom'
import { api } from './api/client'
import Archiwum from './pages/Archiwum'
import Kalendarz from './pages/Kalendarz'
import Konto from './pages/Konto'
import Logowanie from './pages/Logowanie'
import NowyWniosek from './pages/NowyWniosek'
import Sprawa from './pages/Sprawa'
import Uzytkownicy from './pages/Uzytkownicy'

const NAV = [
  { to: '/', label: 'Kalendarz', end: true },
  { to: '/nowy', label: 'Nowy wniosek' },
  { to: '/archiwum', label: 'Archiwum i wiedza' },
]

function NieZnaleziono() {
  return (
    <section>
      <h1>Nie znaleziono strony</h1>
      <p><Link to="/">← Wróć do kalendarza</Link></p>
    </section>
  )
}

function LlmStatus({ health }) {
  if (!health) return null
  const { llm } = health
  const tekst = llm.dostepny ? `AI: ${llm.model}` : 'AI niedostępne – tryb bez AI'
  return (
    <span className={`pill ${llm.dostepny ? 'pill-ok' : 'pill-muted'}`} title={`Backend LLM: ${llm.backend}`}>
      {tekst}
    </span>
  )
}

export default function App() {
  const [health, setHealth] = useState(null)
  // undefined = sprawdzam sesję, null = niezalogowany, obiekt = /auth/ja
  const [ja, setJa] = useState(undefined)
  const navigate = useNavigate()

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null))
    api.ja().then(setJa).catch(() => setJa(null))
    const wygasla = () => setJa(null)
    window.addEventListener('sesja-wygasla', wygasla)
    return () => window.removeEventListener('sesja-wygasla', wygasla)
  }, [])

  async function wyloguj() {
    await api.wyloguj().catch(() => {})
    setJa(null)
  }

  // Zakończone logowanie (ostatni krok na ekranie logowania) -> zawsze kalendarz,
  // niezależnie od adresu sprzed wylogowania / wygaśnięcia sesji.
  function poKrokuLogowania(nowe) {
    setJa(nowe)
    if (nowe?.stan === 'OK') navigate('/', { replace: true })
  }

  if (ja === undefined) return <div className="auth-wrap"><span className="spinner" aria-label="Ładowanie" /></div>
  if (ja === null || ja.stan !== 'OK') return <Logowanie ja={ja} onZmiana={poKrokuLogowania} />

  const nav = ja.rola === 'admin' ? [...NAV, { to: '/uzytkownicy', label: 'Użytkownicy' }] : NAV

  return (
    <div className="app">
      {health?.llm?.zewnetrzny && (
        <div className="banner banner-danger" role="alert">
          Tryb deweloperski: model językowy działa poza urzędem (zewnętrzne API). Nie wgrywaj prawdziwych danych.
        </div>
      )}
      <header className="topbar">
        <div className="brand">
          <img className="brand-logo" src="/logo.png" alt="Bydgoszcz" />
          <div>
            <div className="brand-title">Asystent urzędnika</div>
            <div className="brand-sub">Urząd Miasta Bydgoszczy · Biuro Komunikacji Społecznej</div>
          </div>
        </div>
        <nav className="nav" aria-label="Główna nawigacja">
          {nav.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => (isActive ? 'active' : '')}>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <LlmStatus health={health} />
        <div className="user-menu">
          <NavLink to="/konto" className={({ isActive }) => `user-link ${isActive ? 'active' : ''}`} title="Moje konto">
            {ja.login}
          </NavLink>
          <button type="button" className="btn btn-small" onClick={wyloguj}>Wyloguj</button>
        </div>
      </header>

      <main className="content">
        <Routes>
          <Route path="/" element={<Kalendarz />} />
          <Route path="/nowy" element={<NowyWniosek />} />
          <Route path="/sprawy/:id" element={<Sprawa ja={ja} />} />
          <Route path="/archiwum" element={<Archiwum />} />
          <Route path="/konto" element={<Konto ja={ja} onZmiana={setJa} />} />
          {ja.rola === 'admin' && <Route path="/uzytkownicy" element={<Uzytkownicy ja={ja} onZmiana={setJa} />} />}
          <Route path="*" element={<NieZnaleziono />} />
        </Routes>
      </main>
    </div>
  )
}
