# Frontend – Asystent UDIP

React 19 + Vite. Kontrakt z backendem: [../backend/docs/APIDOC.md](../backend/docs/APIDOC.md).

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # dist/ – serwowane przez FastAPI w obrazie Dockera
```

`VITE_API_MOCK=1` (domyślnie w `.env.development`) – dane z `src/api/mock.js`, bez backendu.
Ustaw `VITE_API_MOCK=0` w `.env.development.local`, gdy backend działa na `localhost:8000` (proxy `/api`).

Mock trzyma stan w pamięci przeglądarki – odświeżenie strony przywraca dane początkowe.
