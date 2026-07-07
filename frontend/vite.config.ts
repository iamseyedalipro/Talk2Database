/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  define: {
    // react-draggable (used by react-grid-layout) reads process.env.DRAGGABLE_DEBUG
    // when a drag starts; without this define the bare `process` reference throws
    // in the browser and every dashboard drag/resize silently aborts.
    'process.env.DRAGGABLE_DEBUG': 'false',
  },
  server: {
    port: 5173,
    proxy: {
      // Forward all API traffic to the FastAPI backend during development.
      // In Docker dev (docker-compose.dev.yml) VITE_API_HOST=http://panel:8000.
      '/api': {
        target: process.env.VITE_API_HOST ?? 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: false,
  },
});
