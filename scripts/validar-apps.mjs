// Valida src/data/apps.json. Falla (exit 1) si hay errores; solo avisa con las advertencias.
// Uso: npm run validar   (también corre solo antes de `npm run build`)
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const raiz = join(dirname(fileURLToPath(import.meta.url)), '..');
const archivo = join(raiz, 'src', 'data', 'apps.json');

const ESTADOS = ['produccion', 'desarrollo', 'demo', 'prototipo', 'por-confirmar', 'privado'];
const VISIBILIDAD = ['publica', 'oculta'];
const OBLIGATORIOS = [
  'slug',
  'nombre',
  'categoria',
  'estado',
  'visibilidad',
  'destacado',
  'autorizado',
  'resumen',
  'problema',
  'solucion',
  'tecnologias',
  'enlace',
  'healthUrl',
];

// Patrones de secretos evidentes (no es un escáner completo; es una red de seguridad).
const SECRETOS = [
  [/AKIA[0-9A-Z]{16}/, 'llave de AWS'],
  [/ghp_[A-Za-z0-9]{20,}/, 'token de GitHub'],
  [/sk-[A-Za-z0-9]{20,}/, 'llave tipo API (sk-...)'],
  [/-----BEGIN [A-Z ]*PRIVATE KEY-----/, 'llave privada'],
  [/[a-z]+:\/\/[^\s:@"]+:[^\s@"]+@/i, 'URL con usuario y contraseña'],
  [/"(password|passwd|secret|token|api[_-]?key)"\s*:\s*"[^"]+"/i, 'campo de credencial con valor'],
  [/(^|[^\d])(10|192\.168|172\.(1[6-9]|2\d|3[01]))\.\d+\.\d+/, 'IP privada'],
  [/\/home\/[a-z0-9_-]+\//i, 'ruta local del equipo'],
];

const errores = [];
const avisos = [];

let texto;
let datos;
try {
  texto = await readFile(archivo, 'utf8');
  datos = JSON.parse(texto);
} catch (e) {
  console.error(`[validar] No se pudo leer ${archivo}: ${e.message}`);
  process.exit(1);
}

if (!Array.isArray(datos.apps)) {
  console.error('[validar] apps.json debe tener un arreglo "apps".');
  process.exit(1);
}

for (const [patron, que] of SECRETOS) {
  if (patron.test(texto)) errores.push(`apps.json parece contener ${que}. Quítalo.`);
}

const vistos = new Set();
for (const [i, a] of datos.apps.entries()) {
  const id = a.slug || `#${i + 1}`;
  const e = (m) => errores.push(`[${id}] ${m}`);
  const w = (m) => avisos.push(`[${id}] ${m}`);

  for (const campo of OBLIGATORIOS) if (!(campo in a)) e(`falta el campo "${campo}"`);

  if (a.slug) {
    if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(a.slug)) e('slug debe ser minúsculas con guiones');
    if (vistos.has(a.slug)) e('slug repetido');
    vistos.add(a.slug);
  }
  if (a.estado && !ESTADOS.includes(a.estado)) e(`estado inválido "${a.estado}"`);
  if (a.visibilidad && !VISIBILIDAD.includes(a.visibilidad)) e(`visibilidad inválida "${a.visibilidad}"`);
  if (typeof a.destacado !== 'boolean') e('destacado debe ser true/false');
  if (typeof a.autorizado !== 'boolean') e('autorizado debe ser true/false');
  if (!Array.isArray(a.tecnologias)) e('tecnologias debe ser un arreglo');

  if (a.visibilidad === 'publica') {
    if (a.autorizado !== true) e('es pública pero autorizado no es true (falta el permiso)');
    if (!a.problema?.trim()) e('es pública pero no tiene problema');
    if (!a.solucion?.trim()) e('es pública pero no tiene solución');
    if (Array.isArray(a.tecnologias) && a.tecnologias.length === 0) w('pública sin tecnologías');
    if (a.estado === 'por-confirmar') w('pública con estado por-confirmar');
  }
  if (a.destacado === true && a.visibilidad !== 'publica') e('destacado requiere visibilidad pública');
  if (a.destacado === true && typeof a.ordenDestacado !== 'number') e('destacado requiere ordenDestacado numérico');
  if (a.enlace && !/^https:\/\//.test(a.enlace)) e('enlace debe empezar por https://');
  if (a.healthUrl && !/^https:\/\//.test(a.healthUrl)) e('healthUrl debe empezar por https://');
  if (a.revisar === true) w('marcado "revisar": confirma estado y datos');
}

const resumen = `${datos.apps.length} aplicativos`;
if (avisos.length) console.warn(`[validar] ${avisos.length} aviso(s):\n  - ${avisos.join('\n  - ')}`);
if (errores.length) {
  console.error(`[validar] ${errores.length} error(es) en ${resumen}:\n  - ${errores.join('\n  - ')}`);
  process.exit(1);
}
console.log(`[validar] OK: ${resumen}.`);
