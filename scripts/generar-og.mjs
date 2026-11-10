// Genera public/og.png (1200x630) para compartir en redes.
// Uso: npm run og   — Requiere `sharp` (ya está en devDependencies).
// Si prefieres una imagen diseñada por ti, simplemente reemplaza public/og.png (1200x630).
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import sharp from 'sharp';

const raiz = join(dirname(fileURLToPath(import.meta.url)), '..');
const icono = await readFile(join(raiz, 'public', 'icono.svg'));
const iconoUri = `data:image/svg+xml;base64,${icono.toString('base64')}`;

// Curvas de nivel determinísticas (misma idea que TopoFondo.astro)
function anillo(cx, cy, radio, fase, amp) {
  const pts = [];
  const N = 64;
  for (let i = 0; i < N; i++) {
    const a = (i / N) * Math.PI * 2;
    const ruido = Math.sin(3 * a + fase) * 0.5 + Math.sin(5 * a + fase * 1.7) * 0.3 + Math.sin(2 * a + fase * 0.6) * 0.4;
    const r = radio * (1 + amp * ruido);
    pts.push(`${(cx + r * Math.cos(a) * 1.35).toFixed(1)} ${(cy + r * Math.sin(a)).toFixed(1)}`);
  }
  return `M${pts.join('L')}Z`;
}
const trazos = Array.from({ length: 16 }, (_, i) => anillo(920, 250, (i + 1) * 30, 3 + i * 0.22, 0.05 + i * 0.012));

const svg = `
<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <rect width="1200" height="630" fill="#0B1F2A"/>
  <g fill="none" stroke="#7FD6CB" stroke-opacity="0.18" stroke-width="1.5">
    ${trazos.map((d) => `<path d="${d}"/>`).join('')}
  </g>
  <image href="${iconoUri}" x="860" y="130" width="260" height="260"/>
  <text x="72" y="130" font-family="'JetBrains Mono', 'DejaVu Sans Mono', monospace" font-size="26" letter-spacing="5" fill="#7FD6CB">SOFTWARE DATA LAB</text>
  <text font-family="'Space Grotesk', 'Helvetica Neue', Arial, sans-serif" font-size="76" font-weight="700" fill="#F4F7F6">
    <tspan x="72" y="260">Software a la medida</tspan>
    <tspan x="72" y="350">para cualquier sector</tspan>
  </text>
  <text x="72" y="430" font-family="'Space Grotesk', 'Helvetica Neue', Arial, sans-serif" font-size="32" fill="#B4C4C7">Software, analítica, IA e IoT desde Medellín.</text>
  <rect x="72" y="500" width="360" height="64" rx="10" fill="#F2A93B"/>
  <text x="252" y="541" text-anchor="middle" font-family="'Space Grotesk', 'Helvetica Neue', Arial, sans-serif" font-size="27" font-weight="700" fill="#0B1F2A">Diagnóstico gratis</text>
  <text x="1128" y="548" text-anchor="end" font-family="'JetBrains Mono', 'DejaVu Sans Mono', monospace" font-size="24" fill="#9BE5DA">sdl.danielflorez.dev</text>
</svg>`;

const png = await sharp(Buffer.from(svg)).png({ palette: true, compressionLevel: 9, quality: 90 }).toBuffer();
await writeFile(join(raiz, 'public', 'og.png'), png);
console.log(`public/og.png generado (${(png.length / 1024).toFixed(0)} KB)`);
