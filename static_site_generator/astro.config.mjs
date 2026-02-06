// @ts-check
import { defineConfig } from 'astro/config';

// https://astro.build/config
export default defineConfig({
  site: 'https://plants.cynexia.com',
  outDir: './dist',
  publicDir: './public',
  build: {
    assets: '_astro'
  }
});
