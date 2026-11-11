import registro from '../data/apps.json';

export type App = (typeof registro.apps)[number];

/** Etiquetas de estado para mostrar en la web. */
const ETIQUETAS_ESTADO: Record<string, string> = {
  produccion: 'En producción',
  desarrollo: 'En desarrollo',
  demo: 'Demo',
  prototipo: 'Prototipo',
  privado: 'Privado',
};

/** Aplicativos que pueden mostrarse en público: visibles y con autorización. Única regla de publicación. */
export const publicas = (): App[] =>
  registro.apps.filter((a) => a.visibilidad === 'publica' && a.autorizado === true);

const orden = (a: App): number => (a as { ordenDestacado?: number }).ordenDestacado ?? 99;

/** Casos de la landing: públicos, destacados y ordenados. */
export const destacadas = (): App[] =>
  publicas()
    .filter((a) => a.destacado)
    .sort((a, b) => orden(a) - orden(b));

/** Estado legible; null si aún está "por-confirmar" (no se muestra al público). */
export const etiquetaEstado = (a: App): string | null => ETIQUETAS_ESTADO[a.estado] ?? null;
