// Sincroniza el formulario de diagnóstico con la API y comprueba que la política de datos sea una versión conocida.
//
//  1. Genera api/app/opciones.json desde src/data/diagnostico.json. La API lo usa para aceptar solo valores
//     que existen de verdad (sector, tamaño, urgencia y respuestas propias de cada servicio).
//  2. Falla (exit 1) si la versión de src/data/politica.json no está en POLITICAS_VALIDAS de api/app/main.py.
//
// Uso: npm run sincronizar   (también corre solo antes de `npm run build`)
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const raiz = join(dirname(fileURLToPath(import.meta.url)), '..');
const leerJson = async (ruta) => JSON.parse(await readFile(join(raiz, ruta), 'utf8'));

const diagnostico = await leerJson('src/data/diagnostico.json');
const politica = await leerJson('src/data/politica.json');
const mainPy = await readFile(join(raiz, 'api', 'app', 'main.py'), 'utf8');

// --- política: la versión publicada debe estar en la lista de la API --------------------------------------
const bloque = mainPy.match(/POLITICAS_VALIDAS\s*=\s*\(([^)]*)\)/);
if (!bloque) {
  console.error('ERROR: no encuentro POLITICAS_VALIDAS en api/app/main.py');
  process.exit(1);
}
const versiones = [...bloque[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
if (!versiones.includes(politica.version)) {
  console.error(
    `ERROR: la política es la versión "${politica.version}" pero la API solo acepta ${JSON.stringify(versiones)}.\n` +
      '       Agrega la versión nueva a POLITICAS_VALIDAS en api/app/main.py (conserva las anteriores para las páginas en caché).',
  );
  process.exit(1);
}

// --- opciones válidas para la API ------------------------------------------------------------------------
const opciones = {
  _ayuda: 'GENERADO por scripts/sincronizar-api.mjs desde src/data/diagnostico.json. No lo edites a mano: ejecuta `npm run sincronizar`.',
  sectores: diagnostico.sectores,
  tamanos: diagnostico.tamanos,
  urgencias: diagnostico.urgencias,
  detalle: Object.fromEntries(diagnostico.servicios.flatMap((s) => s.preguntas.map((p) => [p.id, p.opciones]))),
};

await writeFile(join(raiz, 'api', 'app', 'opciones.json'), JSON.stringify(opciones, null, 2) + '\n', 'utf8');
console.log(
  `sincronizar-api: opciones.json actualizado (${Object.keys(opciones.detalle).length} preguntas propias, política ${politica.version}).`,
);
