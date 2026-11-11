import site from '../data/site.json';

export { site };

/** true cuando el valor está vacío (aún sin llenar). */
export const vacio = (v: string | undefined | null): boolean => !v || v.trim() === '';

/** Número de WhatsApp solo con dígitos. */
const numeroWhatsapp = (): string => (site.contacto.whatsapp || '').replace(/\D/g, '');

export const whatsappListo = (): boolean => numeroWhatsapp().length >= 8;

/**
 * Enlace de WhatsApp con mensaje prellenado.
 * Si el número aún no está configurado, lleva al formulario de contacto.
 */
export function whatsappUrl(mensaje?: string): string {
  const numero = numeroWhatsapp();
  if (numero.length < 8) return '/#contacto';
  const texto = mensaje ?? site.contacto.mensajeWhatsapp;
  return `https://wa.me/${numero}?text=${encodeURIComponent(texto)}`;
}

export const correoListo = (): boolean => !vacio(site.contacto.correo);

export const correoUrl = (): string =>
  correoListo() ? `mailto:${site.contacto.correo.trim()}` : '/#contacto';

/** Todas las redes, configuradas o no (para mostrar pendientes en desarrollo). */
export const todasLasRedes = () =>
  [
    { id: 'facebook', nombre: 'Facebook', url: site.redes.facebook },
    { id: 'instagram', nombre: 'Instagram', url: site.redes.instagram },
    { id: 'youtube', nombre: 'YouTube', url: site.redes.youtube },
  ] as const;

/** Redes configuradas (se omiten las vacías). */
export const redesActivas = () => todasLasRedes().filter((r) => !vacio(r.url));

/** Los marcadores de "pendiente" solo se ven mientras desarrollas (npm run dev). */
export const mostrarPendientes: boolean = import.meta.env.DEV;
