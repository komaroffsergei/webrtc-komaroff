import { defineConfig } from 'vite';

export default defineConfig({
  root: '.',
  publicDir: 'public',
  build: {
    outDir: '../dist',
    rollupOptions: {
      input: './src/main.ts',
    },
  },
  server: {
    port: 3000,
    open: false,
    host: '0.0.0.0',
  },
});