import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  // Load the correct .env file for the current mode:
  //   npm run dev   → .env.development  (or .env.localhost if you copy it)
  //   npm run build → .env.production   (or .env if you copy it)
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [react()],

    // Make all VITE_ vars available in the app
    define: {
      __APP_MODE__: JSON.stringify(mode),
    },

    server: {
      port: 5173,
      open: true,
      // Dev proxy: in development mode, forward /api requests to the local
      // Uvicorn backend so you never need to touch CORS or .env for local work.
      proxy: mode === 'development' ? {
        '/api': {
          target: env.VITE_API_URL || 'http://127.0.0.1:5050',
          changeOrigin: true,
          secure: false,
          // Handle SSE: prevent the Vite dev-server from buffering the stream.
          // Without this, SSE events arrive all at once when the connection closes.
          configure: (proxy) => {
            proxy.on('proxyRes', (proxyRes, req) => {
              const ct = proxyRes.headers['content-type'] || '';
              if (ct.includes('text/event-stream')) {
                proxyRes.headers['x-accel-buffering'] = 'no';
                proxyRes.headers['cache-control'] = 'no-cache, no-transform';
                // Remove content-encoding so the stream is not gzip-compressed
                delete proxyRes.headers['content-encoding'];
              }
            });
          },
        },
      } : undefined,
    },

    build: {
      outDir: 'dist',
      sourcemap: mode === 'development',  // source maps only for dev builds
      rollupOptions: {
        output: {
          // Split vendor chunks to keep the main bundle small
          manualChunks: {
            vendor: ['react', 'react-dom', 'react-router-dom'],
            charts: ['recharts'],
            icons: ['lucide-react'],
          },
        },
      },
    },
  }
})
