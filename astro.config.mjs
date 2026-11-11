// @ts-check
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';

// https://astro.build/config
export default defineConfig({
  // Dominio final: se usa para el sitemap, canonical y Open Graph.
  site: 'https://sdl.danielflorez.dev',
  output: 'static',
  integrations: [sitemap()],
  vite: {
    plugins: [tailwindcss()],
    // Solo para `npm run dev`: reenvía /api al contenedor local (docker compose en api/, puerto 8010).
    server: { proxy: { '/api': 'http://127.0.0.1:8010' } },
  },
});
