import { useEffect, useState } from 'react'
import { Link, NavLink, Route, Routes } from 'react-router-dom'
import { api } from './api/client'
import Archiwum from './pages/Archiwum'
import Kalendarz from './pages/Kalendarz'
import NowyWniosek from './pages/NowyWniosek'
import Sprawa from './pages/Sprawa'

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

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null))
  }, [])

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
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => (isActive ? 'active' : '')}>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <LlmStatus health={health} />
      </header>

      <main className="content">
        <Routes>
          <Route path="/" element={<Kalendarz />} />
          <Route path="/nowy" element={<NowyWniosek />} />
          <Route path="/sprawy/:id" element={<Sprawa />} />
          <Route path="/archiwum" element={<Archiwum />} />
          <Route path="*" element={<NieZnaleziono />} />
        </Routes>
      </main>
    </div>
  )
}
