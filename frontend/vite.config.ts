import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({command, mode}) => {
  const env = loadEnv(mode, process.cwd(), '')
  if (command === 'build' && env.RENDER_SERVICE_TYPE === 'static') {
    const url = URL.canParse(env.VITE_API_BASE_URL || '') ? new URL(env.VITE_API_BASE_URL) : null
    if (!url || url.protocol !== 'https:' || url.username || url.password || url.search || url.hash || url.pathname === '/') {
      throw new Error('Set VITE_API_BASE_URL to the public HTTPS API endpoint, including its /api path.')
    }
  }
  return {
    plugins: [react(), tailwindcss()],
    server: {
      proxy: {
        '/api': {target: env.API_PROXY_TARGET || 'http://127.0.0.1:8000'},
        '/health': {target: env.API_PROXY_TARGET || 'http://127.0.0.1:8000'},
      },
    },
  }
})
