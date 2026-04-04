import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// Proxy target: localhost for `npm run dev` on your machine; http://api:5000 inside Docker Compose.
const apiProxyTarget =
  process.env.VITE_DEV_API_PROXY?.trim() || 'http://localhost:5000';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@components': path.resolve(__dirname, './src/components'),
      '@hooks': path.resolve(__dirname, './src/hooks'),
      '@api': path.resolve(__dirname, './src/api'),
      '@pages': path.resolve(__dirname, './src/pages'),
      '@types': path.resolve(__dirname, './src/types'),
      '@assets': path.resolve(__dirname, './src/assets'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
    watch: process.env.VITE_DOCKER_DEV
      ? { usePolling: true, interval: 300 }
      : undefined,
  },
});
