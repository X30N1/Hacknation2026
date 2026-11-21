# Frontend – Asystent UDIP

React 19 + Vite. Kontrakt z backendem: [../backend/docs/APIDOC.md](../backend/docs/APIDOC.md).

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # dist/ – serwowane przez FastAPI w obrazie Dockera
```

Frontend wymaga działającego backendu na `localhost:8000` (proxy `/api` w `vite.config.js`).
