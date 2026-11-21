export default function WPrzygotowaniu({ tytul, opis }) {
  return (
    <section>
      <h1>{tytul}</h1>
      <div className="card empty">
        <p>{opis}</p>
        <p className="muted">Ten widok jest w przygotowaniu.</p>
      </div>
    </section>
  )
}
