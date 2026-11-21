// Ostrzeżenie przy niepewnym OCR (np. wniosek pisany odręcznie) – urzędnik poprawia tekst ręcznie.
export default function OcrBaner({ dokument }) {
  if (dokument.metoda !== 'OCR' || dokument.ocr_pewnosc == null || dokument.ocr_pewnosc >= 0.6) return null
  return (
    <div className="banner banner-warn" role="status">
      Tekst odczytany ze skanu jest niepewny ({Math.round(dokument.ocr_pewnosc * 100)}%). Porównaj go z oryginałem i popraw
      przed dalszą pracą (np. wniosek pisany odręcznie).
    </div>
  )
}
