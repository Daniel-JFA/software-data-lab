# Software Data Lab — Landing

Sitio estático con **Astro 7 + Tailwind CSS 4**. Sin backend ni base de datos: los formularios usan Formspree.
Destino: `https://sdl.danielflorez.dev`

## Comandos

```bash
npm install        # una sola vez
npm run dev        # http://localhost:4321  (muestra marcadores [PENDIENTE])
npm run build      # genera /dist (los marcadores se ocultan)
npm run preview    # sirve /dist para probar
npm run og         # regenera public/og.png (1200x630)
```

## Estructura

```
├── astro.config.mjs        # site + sitemap + Tailwind
├── public/
│   ├── logo.svg  icono.svg  favicon.svg   # PLACEHOLDERS: reemplázalos por los tuyos
│   ├── og.png                             # imagen para compartir (1200x630)
│   ├── robots.txt
│   └── clientes/                          # logos de clientes autorizados
├── scripts/generar-og.mjs
└── src/
    ├── data/               # ← AQUÍ EDITAS TODO EL CONTENIDO
    │   ├── site.json       # WhatsApp, correo, redes, Formspree, textos de Inicio/Contacto/pie, SEO
    │   ├── apps.json       # registro único de aplicativos (alimenta los Casos); valida con `npm run validar`
    │   ├── servicios.json  clientes.json  casos.json
    │   ├── lab.json  curso.json  proceso.json
    ├── components/         # una sección por archivo (no necesitas tocarlos)
    ├── layouts/Base.astro  # <head>, SEO, fuentes, analítica comentada
    ├── lib/site.ts         # helpers (enlace de WhatsApp, marcadores pendientes)
    ├── scripts/interacciones.ts  # menú, eventos de analítica, formularios
    ├── styles/global.css   # tokens de marca (colores, fuentes)
    └── pages/index.astro
```

## Formularios (Formspree)

1. Crea cuenta en formspree.io y dos formularios: **Contacto** y **Curso (lista de espera)**.
2. Copia el ID de cada uno (`https://formspree.io/f/XXXXXXXX` → `XXXXXXXX`).
3. Pégalos en `src/data/site.json` → `formularios.contactoFormspreeId` y `formularios.cursoFormspreeId`.

Incluyen campo trampa anti-bots. Mientras el ID esté vacío, el formulario avisa que aún no está activo.

> El formulario de contacto pide además "Correo o WhatsApp para responderte"; sin ese dato no hay cómo contestar.

## Analítica

El script está comentado en `src/layouts/Base.astro`. Quita los comentarios de **una** opción (Plausible o GA4).
Los eventos ya están conectados:

| Evento | Cuándo |
|---|---|
| `whatsapp_click` | Cualquier botón de WhatsApp (propiedad `ubicacion`: hero, header, menu-movil, contacto, flotante) |
| `formulario_enviado` | Envío exitoso del formulario de contacto |
| `suscripcion_curso` | Envío exitoso de la lista de espera |
| `correo_click` | Clic en el correo |

En Plausible, declara `whatsapp_click`, `formulario_enviado` y `suscripcion_curso` como *goals*.

## Despliegue con el subdominio sdl.danielflorez.dev

El sitio es estático: el resultado de `npm run build` es la carpeta `dist/`, que cualquier servidor web puede servir. Se publica en tu propio servidor.

1. **DNS** de `danielflorez.dev`: registro `A` (y `AAAA` si usas IPv6) · nombre `sdl` · valor la IP pública de tu servidor.
2. **Compilar** (en tu máquina o en el servidor): `npm ci && npm run build`.
3. **Copiar** `dist/` al servidor, por ejemplo: `rsync -az --delete dist/ usuario@servidor:/var/www/sdl/`.
4. **Servidor web** (ejemplo con nginx, con las cabeceras de seguridad y la caché de los archivos con hash):

```nginx
server {
    listen 80;
    server_name sdl.danielflorez.dev;
    root /var/www/sdl;
    index index.html;

    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;

    location /_astro/ {
        add_header Cache-Control "public, max-age=31536000, immutable";
        access_log off;
    }

    location / {
        try_files $uri $uri/ =404;
    }
}
```

5. **HTTPS** con Let's Encrypt: `sudo certbot --nginx -d sdl.danielflorez.dev`.

> Si repites las cabeceras dentro de un `location` con `add_header`, nginx descarta las del nivel superior; vuelve a declararlas ahí. Si usas Caddy o Apache, aplica las mismas cabeceras.

Después de publicar, verifica: `https://sdl.danielflorez.dev/sitemap-index.xml` y `/robots.txt`, y prueba el enlace en el depurador de Facebook (Sharing Debugger) para refrescar la vista previa.

## Lista de verificación antes de publicar

- [ ] **WhatsApp**: `site.json` → `contacto.whatsapp` (solo dígitos con indicativo, ej. `573001234567`) y `whatsappVisible`.
- [ ] **Mensaje prellenado** de WhatsApp: revisa `contacto.mensajeWhatsapp`.
- [ ] **Correo**: `site.json` → `contacto.correo`.
- [ ] **Redes**: `site.json` → `redes.facebook`, `redes.instagram`, `redes.youtube`.
- [ ] **Formspree**: los dos IDs en `site.json` → `formularios`.
- [ ] **Logos de marca**: reemplaza `public/logo.svg`, `icono.svg`, `favicon.svg` (los actuales son provisionales).
- [ ] **Imagen para compartir**: revisa `public/og.png` (o reemplázala por tu diseño de 1200×630).
- [ ] **Logos de clientes**: solo los autorizados, en `src/data/clientes.json` + `public/clientes/`. Vacío = el bloque se oculta.
- [ ] **Casos** (`casos.json`): revisa los textos (son borradores sin cifras), completa tecnologías de RentMotor y la plataforma GPS, y agrega enlaces. Sin enlace, el botón se oculta.
- [ ] **Curso** (`curso.json`): cambia los títulos de las 6 lecciones por los reales.
- [ ] **Series del Lab** (`lab.json`): confirma nombres y descripciones.
- [ ] **Analítica**: activa Plausible o GA4 en `Base.astro`.
- [ ] Corre `npm run dev` y busca cualquier `[PENDIENTE]` en pantalla; deben desaparecer todos.
- [ ] Corre Lighthouse (móvil) sobre la URL publicada.
