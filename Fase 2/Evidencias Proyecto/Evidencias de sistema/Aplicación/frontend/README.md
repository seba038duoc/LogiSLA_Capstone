# LogiSLA — frontend

Next.js (App Router) + Tailwind CSS v4. Se conecta al backend FastAPI definido en
`NEXT_PUBLIC_API_URL` (`.env.local`, por defecto `http://localhost:8000`).

```bash
npm install
npm run dev      # http://localhost:3000
```

## Estructura

```
app/
  layout.tsx          cabecera, proveedor de empresa, tipografía
  globals.css         sistema de diseño: colores (claro/oscuro), franja, foco
  page.tsx            /            Lotes
  cargar/page.tsx     /cargar      Cargar envíos
  lotes/[id]/page.tsx /lotes/{id}  Detalle del lote
components/
  EmpresaContext.tsx  empresa activa (hoy: selector; mañana: login)
  EstadoEmpresa.tsx   estados "cargando / sin conexión / sin empresas"
  SiteHeader.tsx      marca, navegación, selector de empresa
  Franja.tsx          franja de cumplimiento + leyenda
  UploadFlow.tsx      flujo de carga y auditoría
  ui.tsx              botones, avisos, etiquetas, spinner
lib/
  api.ts              cliente del backend y tipos
  formato.ts          pesos, fechas y porcentajes en es-CL
  csv.ts              descarga de incumplimientos
```

## Convenciones de diseño

- Los componentes usan los colores semánticos de `globals.css` (`bg-superficie`,
  `text-tinta`, `text-tinta-suave`, `border-linea`, `bg-accion`...), nunca
  `bg-white` ni `text-slate-*`: así el modo oscuro funciona solo.
- Cada resultado de auditoría tiene siempre el mismo nombre y color:
  en plazo (`cumplido`), fuera de plazo (`incumplido`), en tránsito
  (`transito`), sin regla SLA (`sin-regla`), sin auditar.
- Las cifras llevan la clase `cifras` (números tabulares) y se formatean
  con `lib/formato.ts`.
