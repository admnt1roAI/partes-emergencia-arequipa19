import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  base: process.env.GITHUB_ACTIONS === 'true' ? '/partes-emergencia-arequipa19/' : '/',
  plugins: [react()],
});
