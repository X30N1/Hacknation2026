// Pobieranie plików w przeglądarce (aplikacja niczego nie wysyła – urzędnik zapisuje plik u siebie).
export function pobierzBlob(blob, nazwa) {
  const url = URL.createObjectURL(blob)
  const a = Object.assign(document.createElement('a'), { href: url, download: nazwa })
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function pobierzTekst(tekst, nazwa) {
  pobierzBlob(new Blob([tekst], { type: 'text/plain;charset=utf-8' }), nazwa)
}

export const bezRozszerzenia = (nazwa) => (nazwa || 'dokument').replace(/\.[^.]+$/, '')
