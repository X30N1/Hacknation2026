// „…[trafione] słowo…” z FTS5 snippet() -> tekst z wyróżnionymi (<mark>) trafieniami
export default function Podswietl({ tekst }) {
  return (tekst || '').split(/\[([^\]]*)\]/).map((czesc, i) => (i % 2 ? <mark key={i}>{czesc}</mark> : czesc))
}
