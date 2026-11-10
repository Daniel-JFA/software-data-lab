# Software Data Lab — Plan de sprints

Visión: SDL empieza como la **vitrina** (landing) y crece hasta ser el **centro de control** de todos tus aplicativos: qué existe, en qué estado está, dónde corre, quién lo usa y cuánto cuesta mantenerlo. Se construye por capas, de modo que cada sprint deje algo publicable.

Convención: sprints de 2 semanas, trabajo en solitario (~15–20 h útiles por sprint). IDs `Sx-yy` como en SSE para usarlos en commits (`feat(registro): ... (S2-01)`). Al cerrar cada sprint, actualiza el estado en este archivo.

## 1. Inventario (revisado en `~/Dev/projects/SDL/`)

| Aplicativo | Qué es | Stack | Estado probable | Vitrina pública |
|---|---|---|---|---|
| RentMotor | Alquiler de motos: conductores, pagos, gastos | Express + TS + Prisma + PostgreSQL | Producción (hay `MIGRACION_PRODUCCION.md`) | Sí (caso en landing) |
| VetPro (`Vet`) | Gestión veterinaria + transcripción IA | Angular + Node + PostgreSQL + Whisper | Pre-lanzamiento (`PRE_LAUNCH_AUDIT.md`, `PRODUCCION_RUNBOOK.txt`) | Sí |
| DataHeartSC (`SC`) | ERP/CRM Fundación Santiago Corazón | NestJS + Angular + PostgreSQL/PostGIS + Redis | En desarrollo, cliente real | Con permiso del cliente |
| MedTurn / TURMED | SaaS multitenant de turnos médicos | Backend + frontend + PostgreSQL | Con `entrega_cliente` | Con permiso |
| Compasión 360 | Gestión operativa y contable, 16 módulos | Angular 21 | Prototipo/propuesta | Demo |
| Voluntariado Colombia | Coordinación de emergencias (sismo Chocó) | PostGIS + backend + frontend | Con guía de producción | Sí, con cuidado |
| NEXION | Mensajería WhatsApp + contactos | Flask | Operativo (hay plan SaaS + IA) | Posible |
| TRAMA | Análisis de redes sociales (grafos) | FastAPI + frontend | Plan de trabajo | Demo |
| La Ventanita | POS y fiado por voz en Raspberry Pi | Python (por confirmar) | Diseño/docs | Experimento del Lab |
| Transcrip | Transcripción FastAPI + Angular | FastAPI + Angular | Prototipo | Experimento del Lab |
| Vinks | Plataforma con auditoría y Power BI | Mongo Atlas + Power BI | Traspaso (manual 2026) | Con permiso |
| Web_Asdru, Invitaciones, df-portfolio | Sitios y utilidades | Varios | Entregados/menores | Portafolio |
| Plataforma GPS deportiva | Perfiles físicos | No encontré carpeta | Por ubicar | Sí (caso en landing) |

Fuera del registro público (personales o sensibles): `trading`, `deriv-mcp`, `ghunt`, `maigret`, `theHarvester`, informes OSINT.

**Hallazgos útiles**
- Casi todos tienen `docker-compose.yml` con PostgreSQL propio y su propio login: no hay nada compartido. Eso sube el costo de mantenimiento.
- Documentación desigual: unos tienen `CLAUDE.md`, `PRODUCT.md` y runbooks; otros solo un README.
- El `CLAUDE.md` de `~/Dev` está desactualizado: apunta a `projects/Propios/...` y esas rutas ya no existen (todo está en `projects/SDL/`).
- Revisa que no haya secretos versionados: vi `NEXION/credenciales`, `Vet/GITHUB_SECRETS_INSTRUCTIONS.txt` y `env` en NEXION. No abrí su contenido; confírmalo antes de subir nada a GitHub.
- Ya tienes una `Propuestas/` con plantilla base y biblioteca de componentes: es la semilla del módulo comercial.
- La carpeta `software-data-lab-logo/svg` ya tiene los logos reales para reemplazar los provisionales.

## 2. Recomendación de arquitectura

1. **SDL público = sitio estático** (Astro, lo que ya existe). Sin base de datos.
2. **Un registro único de aplicativos**: `src/data/apps.json` (sin secretos). Es la fuente de verdad: alimenta casos de la landing, páginas de portafolio y el panel interno.
3. **Panel interno separado** (`sdl-control`, privado), no dentro de la landing. Empieza sin servidor propio: un workflow programado (GitHub Actions) hace ping a los `/health` de cada app y escribe `status.json`.
4. **Estándar mínimo por aplicativo**: endpoint `/health` y `/version`, `.env.example`, script de backup, README y runbook con la misma plantilla. Se aplica gradualmente, no a todos de una vez.
5. **No unifiques el login de todo.** Cada cliente tiene datos propios; centraliza solo la *vista de operación* (estado, versiones, vencimientos), no los datos de clientes.
6. **Tope de alcance**: el panel muestra y avisa; no despliega ni administra bases de datos de producción.

## 3. Sprints

### S1 — Publicar la landing (semana 1–2)
Meta: sitio en `sdl.danielflorez.dev`, medible y con marca real.
- S1-01 Reemplazar logos por los de `software-data-lab-logo/svg` y regenerar `og.png`.
- S1-02 Llenar `site.json`: WhatsApp, correo, redes.
- S1-03 Crear los 2 formularios en Formspree y probar envío real.
- S1-04 Activar Plausible y declarar los 3 goals.
- S1-05 Desplegar en Vercel + DNS del subdominio.
- S1-06 Revisión a 375 px en dispositivo real, teclado y Lighthouse móvil ≥ 90 en las 4 categorías.
- S1-07 Reescribir textos de casos y curso con datos reales.
- **Hecho cuando:** URL pública, formularios llegando, evento de WhatsApp visible en analítica.

### S2 — Registro de aplicativos (semana 3–4)
- S2-01 Definir esquema `apps.json`: `slug, nombre, categoria, estado (producción | demo | prototipo | privado), visibilidad (pública | oculta), cliente (opcional), stack[], url, repo, resumen, problema, solución, healthUrl`.
- S2-02 Cargar los ~12 aplicativos con estado real (decide cuáles son públicos).
- S2-03 Que `Casos.astro` lea de `apps.json` (los destacados).
- S2-04 Script `npm run validar` que falla el build si falta un campo o hay un secreto evidente.
- S2-05 Corregir el `CLAUDE.md` del workspace con las rutas reales.
- **Hecho cuando:** agregar un aplicativo = editar una entrada y desplegar.

### S3 — Portafolio y páginas de caso (semana 5–6)
- S3-01 Página `/portafolio` con filtro por categoría y estado.
- S3-02 Página por caso `/casos/[slug]` generada desde el registro, con SEO y Open Graph propios.
- S3-03 Capturas optimizadas (`astro:assets`, WebP/AVIF) con texto alternativo.
- S3-04 Permisos de cada cliente para mostrar su caso (checklist en el registro: `autorizado: true/false`).
- S3-05 Sitemap actualizado y enlaces desde la landing.
- **Hecho cuando:** 3 casos con página completa y Lighthouse se mantiene ≥ 90.

### S4 — Estándar operativo (semana 7–8)
- S4-01 Documento del estándar: `/health`, `/version`, `.env.example`, backup, runbook, plantilla de README.
- S4-02 Piloto en RentMotor: implementar `/health` y `/version`.
- S4-03 Piloto en VetPro: mismo estándar.
- S4-04 Plantilla de backup reutilizable (basada en `voluntariado-colombia/backup_db.sh`) y prueba de restauración.
- S4-05 Auditoría de secretos en los repos (NEXION, Vet, Vinks) y rotación si aplica.
- **Hecho cuando:** 2 aplicativos cumplen el estándar y un backup se restauró con éxito.

### S5 — Panel interno v1: estado (semana 9–10)
- S5-01 Repo privado `sdl-control` (Astro o Next en Vercel) con acceso protegido.
- S5-02 Workflow programado que consulta `healthUrl` de cada app y guarda `status.json`.
- S5-03 Tablero: semáforo por aplicativo, versión desplegada, último chequeo.
- S5-04 Alerta por correo o WhatsApp (reutilizando NEXION / `whatsapp-mcp`) cuando una app cae.
- **Hecho cuando:** apagas una app de prueba y recibes el aviso.

### S6 — Panel v2: operación y costos (semana 11–12)
- S6-01 Campos de operación por aplicativo: hosting, dominio, vencimiento de dominio y SSL, costo mensual, responsable.
- S6-02 Vista de vencimientos próximos (30 días) con aviso.
- S6-03 Último backup y último despliegue por aplicativo.
- S6-04 Resumen mensual: costo de infraestructura vs. ingreso por mantenimiento.
- **Hecho cuando:** ningún dominio, certificado o backup vence sin que te avises.

### S7 — Clientes y soporte (semana 13–14)
- S7-01 Página de estado por cliente (solo sus aplicativos, enlace privado).
- S7-02 Formulario de solicitud de soporte con número de caso.
- S7-03 Registro de incidentes y mejoras por aplicativo.
- S7-04 Plantilla de informe mensual para el cliente.
- **Hecho cuando:** un cliente real consulta estado y abre un caso sin escribirte por WhatsApp.

### S8 — El Lab y el curso (semana 15–16)
- S8-01 Colección de contenido (Astro Content Collections) para tutoriales y noticias.
- S8-02 Sección con los últimos videos de YouTube.
- S8-03 Publicar las 6 lecciones del curso de fútbol con datos.
- S8-04 Migrar la lista de espera a una herramienta de correo (Buttondown o Brevo) con doble confirmación.
- **Hecho cuando:** publicas una lección y la ven sin tocar código.

### S9 — Comercial (semana 17–18)
- S9-01 Generador de propuestas a partir de `Propuestas/PLANTILLA_PROPUESTA_BASE.md` y la biblioteca de componentes.
- S9-02 Seguimiento de prospectos (de formulario/WhatsApp a diagnóstico, propuesta, cierre).
- S9-03 Catálogo de servicios con precios de referencia (solo si decides publicarlos).
- **Hecho cuando:** una propuesta sale en menos de una hora.

### Continuo (todos los sprints)
Seguridad de dependencias, Lighthouse en cada despliegue, copia de seguridad del registro, actualizar este documento.

## 4. Riesgos

| Riesgo | Mitigación |
|---|---|
| Mostrar un cliente sin permiso | Campo `autorizado` obligatorio; la validación bloquea el build |
| Publicar secretos por accidente | S2-04 y S4-05; nada sensible en `apps.json` |
| El panel crece hasta ser otro producto | Regla: solo mostrar y avisar (sección 2, punto 6) |
| Demasiados aplicativos sin mantenimiento | Estado `prototipo` o `privado` explícito; no se publican |
| Trabajo en solitario | Cada sprint termina en algo publicable; si se retrasa, recortar el último punto |

## 5. Decisiones que necesito de ti

1. ¿Cuáles aplicativos son públicos y cuáles tienen permiso del cliente?
2. ¿Dónde está la plataforma GPS deportiva?
3. ¿Dónde corre cada aplicativo hoy (VPS, Vercel, Railway, local)? Define cómo se hace el chequeo de salud en S5.
4. ¿El panel es solo para ti o también lo verán clientes? Cambia la autenticación de S5 y S7.
