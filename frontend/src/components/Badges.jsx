import { PILNOSC, STATUS } from '../lib/labels'

export function StatusBadge({ status, przedluzenieDni }) {
  const s = STATUS[status] || { label: status, kod: '' }
  const dni = status === 'PRZEDLUZONA' && przedluzenieDni ? ` +${przedluzenieDni} dni` : ''
  return (
    <span className={`status status-${status}`}>
      {s.label}
      {dni}
    </span>
  )
}

export function PilnoscBadge({ pilnosc }) {
  const p = PILNOSC[pilnosc]
  if (!p || !p.label) return null
  return (
    <span className={`pilnosc pilnosc-${pilnosc}`} title={p.opis}>
      {pilnosc === 'PRZEKROCZONY' ? '⚠ ' : pilnosc === 'DZIS' ? '● ' : ''}
      {p.label}
    </span>
  )
}

export function Flagi({ flagi, compact = false }) {
  if (!flagi?.length) return compact ? null : <p className="muted">Brak uwag do danych.</p>
  if (compact) {
    return (
      <span className="flag-count" title={flagi.map((f) => '• ' + f.opis).join('\n')} aria-label={`${flagi.length} uwag do danych`}>
        ⚠ {flagi.length}
      </span>
    )
  }
  return (
    <ul className="flag-list">
      {flagi.map((f, i) => (
        <li key={i}>
          <strong>⚠ {f.opis}</strong>
          {f.propozycja && <div className="muted">Propozycja: {f.propozycja}</div>}
        </li>
      ))}
    </ul>
  )
}
