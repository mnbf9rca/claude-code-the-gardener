// @ts-check
import { defineConfig } from 'astro/config';

import tailwindcss from '@tailwindcss/vite';

// https://astro.dev/config
export default defineConfig({
  output: 'static',
  vite: {
    plugins: [tailwindcss()]
  },
  image: {
    domains: [],
    remotePatterns: [{ protocol: 'https', hostname: '*.r2.dev' }],
  },
});