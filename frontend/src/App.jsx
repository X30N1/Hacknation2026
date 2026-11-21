import { useEffect, useState } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import { api, USE_MOCK } from './api/client'
import Kalendarz from './pages/Kalendarz'
import NowyWniosek from './pages/NowyWniosek'
import Sprawa from './pages/Sprawa'
import WPrzygotowaniu from './pages/WPrzygotowaniu'

const NAV = [
  { to: '/', label: 'Kalendarz', end: true },
  { to: '/nowy', label: 'Nowy wniosek' },
  { to: '/archiwum', label: 'Archiwum' },
  { to: '/ustawienia', label: 'Ustawienia' },
]

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
      {USE_MOCK && (
        <div className="banner banner-info">Tryb demonstracyjny: dane przykładowe, bez połączenia z serwerem.</div>
      )}
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">UDIP</span>
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
          <Route path="/archiwum" element={<WPrzygotowaniu tytul="Archiwum" opis="Import archiwalnych wniosków i odpowiedzi oraz wyszukiwanie podobnych spraw." />} />
          <Route path="/ustawienia" element={<WPrzygotowaniu tytul="Ustawienia" opis="Ustawy i cytowania (Dz. U.), lista wydziałów, model AI." />} />
          <Route path="*" element={<WPrzygotowaniu tytul="Nie znaleziono strony" opis="Wróć do kalendarza." />} />
        </Routes>
      </main>
    </div>
  )
}
