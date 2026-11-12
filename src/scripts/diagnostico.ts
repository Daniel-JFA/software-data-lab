/**
 * Diagnóstico de brecha digital: formulario por pasos, puntaje y envío a /api/diagnostico.
 * Primero el contacto (obligatorio); después uno o varios servicios, de los que dependen las preguntas
 * (bloques [data-bloque] por servicio y [data-dim] por área de brecha digital, esta última sin repetirse).
 * El puntaje que ve la persona es el mismo que recalcula la API (promedio por dimensión, 0 a 100).
 */

type Nivel = { hasta: number; nombre: string; texto: string };
type Dimension = { id: string; titulo: string; preguntas: string[] };
type Config = {
  niveles: Nivel[];
  dimensiones: Dimension[];
  servicios: Record<string, string[]>; // id de servicio -> ids de dimensiones que se miden
  titulos: Record<string, string>; // id de servicio -> nombre
  pistas: Record<string, string>; // sector -> nota orientativa de normativa
};

const form = document.getElementById('dg-form') as HTMLFormElement | null;
const configEl = document.getElementById('dg-config');

if (form && configEl) {
  const config = JSON.parse(configEl.textContent ?? '{}') as Config;
  const pasos = Array.from(form.querySelectorAll<HTMLFieldSetElement>('fieldset[data-paso]'));
  const bloques = Array.from(form.querySelectorAll<HTMLElement>('[data-bloque]'));
  const areas = Array.from(form.querySelectorAll<HTMLElement>('[data-dim]'));
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
    aplicarServicios();
    pasos.forEach((p, i) => (p.hidden = i !== n));
    barras.forEach((b, i) => b.classList.toggle('bg-turquesa', i <= n));
    barras.forEach((b, i) => b.classList.toggle('bg-borde', i > n));
    atras.hidden = n === 0;
    siguiente.hidden = n === pasos.length - 1;
    enviar.hidden = n !== pasos.length - 1;
    mostrarEstado('');
    document.getElementById('dg-tarjeta')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  /* ------------------------------------------------------------ servicios elegidos */
  const casillas = Array.from(form.querySelectorAll<HTMLInputElement>('input[name="servicios"]'));
  const elegidos = (): string[] => casillas.filter((c) => c.checked).map((c) => c.value);

  const mostrarBloque = (bloque: HTMLElement, activo: boolean): void => {
    bloque.hidden = !activo;
    // Lo deshabilitado no se valida ni se envía.
    bloque.querySelectorAll<HTMLInputElement>('input').forEach((i) => {
      i.disabled = !activo;
    });
  };

  const tipoCasillas = Array.from(form.querySelectorAll<HTMLInputElement>('input[name="datos_tipos"]'));
  const tiposElegidos = (): string[] => tipoCasillas.filter((c) => c.checked).map((c) => c.value);
  const sector = form.querySelector<HTMLSelectElement>('#dg-sector');
  const pista = form.querySelector<HTMLElement>('[data-pista]');
  const extras = Array.from(form.querySelectorAll<HTMLElement>('[data-extra]'));

  // Áreas que se preguntan: las de los servicios elegidos sin repetir las compartidas. El gobierno de datos
  // solo se pregunta si la empresa maneja datos de personas (no basta con haber marcado "ninguno").
  const dimensionesActivas = (servicios: string[], tipos: string[]): Set<string> => {
    const dimensiones = new Set(servicios.flatMap((id) => config.servicios[id] ?? []));
    if (tipos.length === 1 && tipos[0] === 'ninguno') dimensiones.delete('gobierno');
    return dimensiones;
  };

  const aplicarServicios = (): void => {
    const ids = elegidos();
    const tipos = tiposElegidos();
    const dimensiones = dimensionesActivas(ids, tipos);
    bloques.forEach((b) => mostrarBloque(b, ids.includes(b.dataset.bloque ?? '')));
    areas.forEach((a) => mostrarBloque(a, dimensiones.has(a.dataset.dim ?? '')));
    // Las preguntas extra de gobierno van después: el área habilita todos sus controles y aquí se apagan
    // las que no corresponden a los tipos de dato marcados.
    extras.forEach((e) => mostrarBloque(e, dimensiones.has('gobierno') && tipos.includes(e.dataset.extra ?? '')));
    if (pista) {
      const texto = config.pistas[sector?.value ?? ''] ?? '';
      pista.textContent = texto;
      pista.hidden = !texto || !dimensiones.has('gobierno');
    }
  };
  casillas.forEach((c) => c.addEventListener('change', aplicarServicios));
  sector?.addEventListener('change', aplicarServicios);
  tipoCasillas.forEach((c) =>
    c.addEventListener('change', () => {
      // "No manejamos datos de personas" es excluyente con el resto de opciones.
      if (c.checked) {
        tipoCasillas.forEach((o) => {
          if (o !== c && (c.value === 'ninguno' || o.value === 'ninguno')) o.checked = false;
        });
      }
      aplicarServicios();
    }),
  );

  /* ------------------------------------------------------------ contacto obligatorio y válido */
  // Mismas reglas que la API (email-validator): sin puntos dobles, dominio con punto, TLD de letras y sin TLD reservados.
  const TLD_RESERVADOS = ['local', 'localhost', 'test', 'invalid', 'example', 'internal', 'lan', 'home', 'corp'];
  const correoValido = (v: string): boolean => {
    if (!/^[A-Za-z0-9._%+'-]+@([A-Za-z0-9-]+\.)+[A-Za-z]{2,}$/.test(v) || v.includes('..')) return false;
    const [usuario, dominio] = v.split('@');
    if (usuario.startsWith('.') || usuario.endsWith('.') || usuario.length > 64) return false;
    return !TLD_RESERVADOS.includes(dominio.split('.').pop()!.toLowerCase());
  };
  const whatsappValido = (v: string): boolean => {
    const digitos = v.replace(/\D/g, '');
    return /^[+\d\s().-]+$/.test(v) && digitos.length >= 7 && digitos.length <= 15;
  };
  const validarContacto = (): void => {
    form.querySelectorAll<HTMLInputElement>('[data-correo]').forEach((c) => {
      c.setCustomValidity(correoValido(c.value.trim()) ? '' : 'Escribe un correo válido, por ejemplo nombre@empresa.com');
    });
    form.querySelectorAll<HTMLInputElement>('[data-whatsapp]').forEach((c) => {
      c.setCustomValidity(
        whatsappValido(c.value.trim()) ? '' : 'Escribe un número de WhatsApp válido, con indicativo (ej. +57 300 123 4567)',
      );
    });
  };

  // Valida solo el paso visible. Los radios obligatorios se comprueban por grupo.
  const pasoValido = (): boolean => {
    validarContacto();
    const paso = pasos[actual];
    // Un grupo de casillas no puede ser "required" en HTML: se exige al menos un servicio a mano.
    if (paso.querySelector('[data-servicios]') && elegidos().length === 0) {
      casillas[0]?.focus();
      mostrarEstado('Elige al menos un servicio para continuar.', true);
      return false;
    }
    if (paso.querySelector('[data-tipos]') && tiposElegidos().length === 0) {
      tipoCasillas[0]?.focus();
      mostrarEstado('Marca qué datos de personas manejan, o "No manejamos datos de personas".', true);
      return false;
    }
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

  const mostrarResultado = (brecha: Record<string, number>, servicios: string[], tipos: string[]): void => {
    const idsDimension = dimensionesActivas(servicios, tipos);
    // En gobierno, las preguntas "extra" solo cuentan si se respondieron (según los tipos de dato marcados).
    const porDimension = config.dimensiones
      .filter((d) => idsDimension.has(d.id))
      .map((d) => ({
        titulo: d.titulo,
        puntos: porcentaje(d.preguntas.filter((p) => p in brecha).map((p) => brecha[p])),
      }));
    document.getElementById('dg-aviso-legal')!.hidden = !idsDimension.has('gobierno');
    const total = porcentaje(Object.values(brecha));
    const nivel = nivelDe(total);

    document.getElementById('dg-servicio')!.textContent = servicios.map((s) => config.titulos[s] ?? s).join(', ');
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

    const waBtn = document.getElementById('dg-wa-btn') as HTMLAnchorElement | null;
    if (waBtn) {
      const empInput = form.querySelector<HTMLInputElement>('[name="empresa"]');
      const emp = empInput?.value.trim() ?? '';
      const msg = `Hola Daniel, completé el diagnóstico de brecha digital en SDL con ${total}/100 (${nivel.nombre})${emp ? ` para ${emp}` : ''}. Quiero revisar los resultados en la sesión de 30 minutos.`;
      waBtn.href = `https://wa.me/573122115299?text=${encodeURIComponent(msg)}`;
    }

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
    const servicios = datos.getAll('servicios').map(String);
    const tipos = datos.getAll('datos_tipos').map(String);
    const brecha: Record<string, number> = {};
    const detalle: Record<string, string> = {};
    // Los nombres tienen la forma "brecha.<pregunta>" o "detalle.<pregunta>". Los controles de lo que no se
    // eligió están deshabilitados y no aparecen aquí.
    for (const [clave, valor] of datos.entries()) {
      const [tipo, id] = clave.split('.');
      if (tipo === 'brecha' && id) brecha[id] = Number(valor);
      else if (tipo === 'detalle' && id) detalle[id] = String(valor);
    }

    const cuerpo = {
      nombre: texto('nombre'),
      empresa: texto('empresa'),
      correo: texto('correo'),
      whatsapp: texto('whatsapp'),
      acepta: datos.get('acepta') === 'on',
      politica: texto('politica'),
      servicios,
      sector: texto('sector'),
      tamano: texto('tamano'),
      datos_tipos: tipos,
      brecha,
      detalle,
      friccion: texto('friccion'),
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
          window.plausible?.('formulario_enviado', { props: { formulario: 'diagnostico', servicios: servicios.join(',') } });
        } catch {
          /* la analítica nunca debe romper la página */
        }
        mostrarResultado(brecha, servicios, tipos);
      } else {
        const json = (await respuesta.json().catch(() => null)) as { detail?: unknown; campo?: unknown; paso?: unknown } | null;
        mostrarEstado(
          typeof json?.detail === 'string' ? json.detail : 'No pudimos enviarlo. Intenta de nuevo o escríbenos por WhatsApp.',
          true,
        );
        // La API señaló un campo concreto: volvemos a su paso y lo enfocamos para corregirlo.
        if (typeof json?.paso === 'number' && json.paso >= 0 && json.paso < pasos.length) {
          irA(json.paso);
          if (typeof json.campo === 'string') {
            form.querySelector<HTMLElement>(`[name="${CSS.escape(json.campo)}"]`)?.focus();
          }
          mostrarEstado(typeof json.detail === 'string' ? json.detail : '', true);
        }
      }
    } catch {
      mostrarEstado('Sin conexión. Intenta de nuevo o escríbenos por WhatsApp.', true);
    } finally {
      enviar.disabled = false;
      enviar.removeAttribute('aria-busy');
    }
  });

  aplicarServicios();
  irA(0);
}

export {};
