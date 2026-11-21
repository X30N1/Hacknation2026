// Klucze sprzętowe (FIDO2 / WebAuthn): konwersja opcji z backendu (base64url) na ArrayBuffer
// dla navigator.credentials i odpowiedzi klucza z powrotem na JSON.
// Działa tylko w bezpiecznym kontekście: HTTPS albo http://localhost.

const b64urlNaBufor = (s) => {
  const b64 = s.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (s.length % 4)) % 4)
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)).buffer
}

const buforNaB64url = (buf) =>
  btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')

export const kluczeDostepne = () => typeof window !== 'undefined' && !!window.PublicKeyCredential && window.isSecureContext

const deskryptory = (lista) => (lista || []).map((c) => ({ ...c, id: b64urlNaBufor(c.id) }))

export async function zarejestrujKlucz(opcje) {
  const cred = await navigator.credentials.create({
    publicKey: {
      ...opcje,
      challenge: b64urlNaBufor(opcje.challenge),
      user: { ...opcje.user, id: b64urlNaBufor(opcje.user.id) },
      excludeCredentials: deskryptory(opcje.excludeCredentials),
    },
  })
  return {
    id: cred.id,
    rawId: buforNaB64url(cred.rawId),
    type: cred.type,
    response: {
      clientDataJSON: buforNaB64url(cred.response.clientDataJSON),
      attestationObject: buforNaB64url(cred.response.attestationObject),
      transports: cred.response.getTransports?.() || [],
    },
    clientExtensionResults: cred.getClientExtensionResults?.() || {},
  }
}

export async function uzyjKlucza(opcje) {
  const cred = await navigator.credentials.get({
    publicKey: {
      ...opcje,
      challenge: b64urlNaBufor(opcje.challenge),
      allowCredentials: deskryptory(opcje.allowCredentials),
    },
  })
  const r = cred.response
  return {
    id: cred.id,
    rawId: buforNaB64url(cred.rawId),
    type: cred.type,
    response: {
      clientDataJSON: buforNaB64url(r.clientDataJSON),
      authenticatorData: buforNaB64url(r.authenticatorData),
      signature: buforNaB64url(r.signature),
      userHandle: r.userHandle ? buforNaB64url(r.userHandle) : null,
    },
    clientExtensionResults: cred.getClientExtensionResults?.() || {},
  }
}

// Czytelny komunikat dla anulowania / przekroczenia czasu (DOMException).
export function bladKlucza(err) {
  if (err?.name === 'NotAllowedError') return 'Operacja anulowana albo czas na dotknięcie klucza minął.'
  if (err?.name === 'InvalidStateError') return 'Ten klucz jest już zarejestrowany.'
  if (err?.name === 'SecurityError') return 'Klucze działają tylko przez HTTPS albo na localhost (sprawdź [auth] rp_id).'
  return err?.message || 'Nie udało się użyć klucza.'
}
