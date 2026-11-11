/**
 * Diagnóstico de brecha digital: formulario por pasos, puntaje y envío a /api/diagnostico.
 * El puntaje que ve la persona es el mismo que recalcula la API (promedio por dimensión, 0 a 100).
 */

type Nivel = { hasta: number; nombre: string; texto: string };
type Dimension = { id: string; titulo: string; preguntas: string[] };
type Config = { niveles: Nivel[]; dimensiones: Dimension[] };

const form = document.getElementById('dg-form') as HTMLFormElement | null;
const configEl = document.getElementById('dg-config');

if (form && configEl) {
  const config = JSON.parse(configEl.textContent ?? '{}') as Config;
  const pasos = Array.from(form.querySelectorAll<HTMLFieldSetElement>('fieldset[data-paso]'));
  const barras = Array.from(document.querySelectorAll<HTMLElement>('[data-progreso] [data-barra]'));
  const atras = document.getElementById('dg-atras') as HTMLButtonElement;
  const siguiente = document.getElementById('dg-siguiente') as HTMLButtonElement;
  const enviar = document.getElementById('dg-enviar') as HTMLButtonElement;
  const estado = form.querySelector<HTMLElement>('[data-estado]');
  let actual = 0;

  const mostrarEstado = (texto: string, error = false): void => {
    if (!estado) return;
    estado.textContent = texto;
    estado.className = `min-h-6 text-sm ${error ? 'text-[#ffb4a8]' : 'text-suave'}`;
  };

  const irA = (n: number): void => {
    actual = n;
    pasos.forEach((p, i) => (p.hidden = i !== n));
    barras.forEach((b, i) => b.classList.toggle('bg-turquesa', i <= n));
    barras.forEach((b, i) => b.classList.toggle('bg-borde', i > n));
    atras.hidden = n === 0;
    siguiente.hidden = n === pasos.length - 1;
    enviar.hidden = n !== pasos.length - 1;
    mostrarEstado('');
    document.getElementById('dg-tarjeta')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  // Valida solo el paso visible. Los radios obligatorios se comprueban por grupo.
  const pasoValido = (): boolean => {
    const paso = pasos[actual];
    for (const campo of Array.from(paso.querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>('input, select, textarea'))) {
      if (!campo.checkValidity()) {
        campo.reportValidity();
        mostrarEstado('Completa los campos obligatorios para continuar.', true);
        return false;
      }
    }
    return true;
  };

  siguiente.addEventListener('click', () => {
    if (pasoValido()) irA(Math.min(actual + 1, pasos.length - 1));
  });
  atras.addEventListener('click', () => irA(Math.max(actual - 1, 0)));

  /* ------------------------------------------------------------ puntaje */
  const porcentaje = (valores: number[]): number =>
    valores.length ? Math.round((valores.reduce((a, b) => a + b, 0) / (valores.length * 3)) * 100) : 0;

  const nivelDe = (puntos: number): Nivel =>
    config.niveles.find((n) => puntos <= n.hasta) ?? config.niveles[config.niveles.length - 1];

  const mostrarResultado = (brecha: Record<string, number>): void => {
    const porDimension = config.dimensiones.map((d) => ({
      titulo: d.titulo,
      puntos: porcentaje(d.preguntas.map((p) => brecha[p] ?? 0)),
    }));
    const total = porcentaje(Object.values(brecha));
    const nivel = nivelDe(total);

    document.getElementById('dg-total')!.textContent = String(total);
    document.getElementById('dg-nivel')!.textContent = nivel.nombre;
    document.getElementById('dg-nivel-texto')!.textContent = nivel.texto;

    const lista = document.getElementById('dg-dimensiones')!;
    lista.replaceChildren(
      ...porDimension.map((d) => {
        const li = document.createElement('li');
        const fila = document.createElement('div');
        fila.className = 'flex items-baseline justify-between gap-3 text-sm';
        const nombre = document.createElement('span');
        nombre.className = 'font-medium text-texto';
        nombre.textContent = d.titulo;
        const valor = document.createElement('span');
        valor.className = 'font-mono text-suave';
        valor.textContent = `${d.puntos} / 100 · ${nivelDe(d.puntos).nombre}`;
        fila.append(nombre, valor);
        const pista = document.createElement('div');
        pista.className = 'mt-1.5 h-2 overflow-hidden rounded-full bg-borde';
        const relleno = document.createElement('div');
        relleno.className = 'h-full rounded-full bg-turquesa';
        relleno.style.width = `${d.puntos}%`;
        pista.append(relleno);
        li.append(fila, pista);
        return li;
      }),
    );

    form.hidden = true;
    document.getElementById('dg-progreso')!.hidden = true;
    document.getElementById('dg-resultado')!.hidden = false;
    document.getElementById('dg-tarjeta')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  /* ------------------------------------------------------------ envío */
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!pasoValido()) return;

    const datos = new FormData(form);
    if (datos.get('_gotcha')) return; // campo trampa para bots

    const texto = (n: string): string => String(datos.get(n) ?? '').trim();
    const brecha: Record<string, number> = {};
    const equipo: Record<string, string> = {};
    for (const [clave, valor] of datos.entries()) {
      if (clave.startsWith('brecha.')) brecha[clave.slice(7)] = Number(valor);
      else if (clave.startsWith('equipo.')) equipo[clave.slice(7)] = String(valor);
    }

    const cuerpo = {
      nombre: texto('nombre'),
      empresa: texto('empresa'),
      contacto: texto('contacto'),
      sector: texto('sector'),
      tamano: texto('tamano'),
      brecha,
      equipo,
      friccion: texto('friccion'),
      servicios: datos.getAll('servicios').map(String),
      urgencia: texto('urgencia'),
      objetivo: texto('objetivo'),
      _gotcha: texto('_gotcha'),
    };

    enviar.disabled = true;
    enviar.setAttribute('aria-busy', 'true');
    mostrarEstado('Enviando…');
    try {
      const respuesta = await fetch(form.dataset.api ?? '', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(cuerpo),
      });
      if (respuesta.ok) {
        try {
          window.plausible?.('formulario_enviado', { props: { formulario: 'diagnostico' } });
        } catch {
          /* la analítica nunca debe romper la página */
        }
        mostrarResultado(brecha);
      } else {
        const json = (await respuesta.json().catch(() => null)) as { detail?: unknown } | null;
        mostrarEstado(
          typeof json?.detail === 'string' ? json.detail : 'No pudimos enviarlo. Intenta de nuevo o escríbenos por WhatsApp.',
          true,
        );
      }
    } catch {
      mostrarEstado('Sin conexión. Intenta de nuevo o escríbenos por WhatsApp.', true);
    } finally {
      enviar.disabled = false;
      enviar.removeAttribute('aria-busy');
    }
  });

  irA(0);
}

export {};
