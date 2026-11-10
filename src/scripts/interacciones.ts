/**
 * Interacciones de la landing: menú móvil, analítica de eventos y formularios (Formspree).
 * Sin dependencias. Se empaqueta y minifica en el build.
 */

type Propiedades = Record<string, string>;

declare global {
  interface Window {
    plausible?: (evento: string, opciones?: { props: Propiedades }) => void;
    gtag?: (...args: unknown[]) => void;
    dataLayer?: unknown[];
  }
}

/* ---------------------------------------------------------------- *
 * Analítica: un solo punto de salida para todos los eventos.
 * Funciona con Plausible o GA4 en cuanto actives el script en Base.astro.
 * ---------------------------------------------------------------- */
function registrarEvento(nombre: string, props: Propiedades = {}): void {
  try {
    window.plausible?.(nombre, { props });
    window.gtag?.('event', nombre, props);
    if (import.meta.env.DEV) console.debug('[evento]', nombre, props);
  } catch {
    /* la analítica nunca debe romper la página */
  }
}

// Cualquier elemento con data-evento="..." registra un evento al hacer clic.
document.addEventListener('click', (e) => {
  const objetivo = (e.target as Element | null)?.closest<HTMLElement>('[data-evento]');
  if (!objetivo) return;
  registrarEvento(objetivo.dataset.evento ?? 'clic', { ubicacion: objetivo.dataset.ubicacion ?? '' });
});

/* ---------------------------------------------------------------- *
 * Menú hamburguesa (móvil)
 * ---------------------------------------------------------------- */
const botonMenu = document.getElementById('menu-boton') as HTMLButtonElement | null;
const menuMovil = document.getElementById('menu-movil');

function alternarMenu(abrir: boolean): void {
  if (!botonMenu || !menuMovil) return;
  menuMovil.hidden = !abrir;
  botonMenu.setAttribute('aria-expanded', String(abrir));
  botonMenu.setAttribute('aria-label', abrir ? 'Cerrar menú' : 'Abrir menú');
  botonMenu.querySelector<HTMLElement>('[data-icono-abrir]')!.hidden = abrir;
  botonMenu.querySelector<HTMLElement>('[data-icono-cerrar]')!.hidden = !abrir;
}

botonMenu?.addEventListener('click', () => alternarMenu(botonMenu.getAttribute('aria-expanded') !== 'true'));

menuMovil?.addEventListener('click', (e) => {
  if ((e.target as Element).closest('[data-cerrar-menu]')) alternarMenu(false);
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && botonMenu?.getAttribute('aria-expanded') === 'true') {
    alternarMenu(false);
    botonMenu.focus();
  }
});

window.matchMedia('(min-width: 1024px)').addEventListener('change', (e) => {
  if (e.matches) alternarMenu(false);
});

/* ---------------------------------------------------------------- *
 * Formularios con Formspree (sin backend propio)
 * ---------------------------------------------------------------- */
type Tipo = 'info' | 'ok' | 'error';

const CLASES_ESTADO: Record<Tipo, string> = {
  info: 'text-suave',
  ok: 'text-turquesa-claro',
  error: 'text-[#ffb4a8]',
};

function mostrarEstado(zona: HTMLElement | null, texto: string, tipo: Tipo): void {
  if (!zona) return;
  zona.className = `min-h-6 text-sm ${CLASES_ESTADO[tipo]}`;
  zona.textContent = texto;
}

document.querySelectorAll<HTMLFormElement>('form[data-formspree]').forEach((form) => {
  const zona = form.querySelector<HTMLElement>('[data-estado]');
  const boton = form.querySelector<HTMLButtonElement>('button[type="submit"]');

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const id = (form.dataset.formspree ?? '').trim();
    if (!id) {
      mostrarEstado(zona, 'Este formulario aún no está activo. Escríbenos por WhatsApp.', 'error');
      return;
    }

    const datos = new FormData(form);
    if (datos.get('_gotcha')) return; // campo trampa para bots

    if (boton) {
      boton.disabled = true;
      boton.setAttribute('aria-busy', 'true');
    }
    mostrarEstado(zona, 'Enviando…', 'info');

    try {
      const respuesta = await fetch(`https://formspree.io/f/${encodeURIComponent(id)}`, {
        method: 'POST',
        body: datos,
        headers: { Accept: 'application/json' },
      });

      if (respuesta.ok) {
        form.reset();
        mostrarEstado(zona, form.dataset.exito ?? 'Enviado.', 'ok');
        registrarEvento(form.dataset.eventoExito ?? 'formulario_enviado', {
          formulario: form.dataset.nombre ?? '',
        });
      } else {
        const cuerpo = (await respuesta.json().catch(() => null)) as { errors?: { message: string }[] } | null;
        const detalle = cuerpo?.errors?.map((x) => x.message).join(' ');
        mostrarEstado(zona, detalle || 'No pudimos enviarlo. Intenta de nuevo o escríbenos por WhatsApp.', 'error');
      }
    } catch {
      mostrarEstado(zona, 'Sin conexión. Intenta de nuevo o escríbenos por WhatsApp.', 'error');
    } finally {
      if (boton) {
        boton.disabled = false;
        boton.removeAttribute('aria-busy');
      }
    }
  });
});

export {};
