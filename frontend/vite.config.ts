import { fileURLToPath } from 'node:url'
import tailwind from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

const frontend = fileURLToPath(new URL('.', import.meta.url))
const project = fileURLToPath(new URL('..', import.meta.url))

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, project, 'ASTRA_DEV_')
  return {
    root: frontend,
    plugins: [
      {
        name: 'astra-exclude-dataset-requests',
        configureServer(server) {
          server.middlewares.use((request, response, next) => {
            const rawPath = (request.url ?? '').split('?')[0]
            let path: string
            try {
              path = decodeURIComponent(rawPath)
            } catch {
              response.statusCode = 400
              response.end('Invalid path')
              return
            }
            if (/(?:^|[/\\])(?:data-source|ASTRA_90day_dataset_v1)(?:[/\\]|$)|\.csv$/i.test(path)) {
              response.statusCode = 404
              response.end('Not found')
              return
            }
            next()
          })
        },
      },
      react(),
      tailwind(),
    ],
    publicDir: false,
    server: {
      host: '127.0.0.1',
      port: Number(env.ASTRA_DEV_FRONTEND_PORT || 5180),
      strictPort: true,
      fs: { strict: true, allow: [frontend] },
      proxy: {
        '^/research-api(?:/|$)': { target: 'http://127.0.0.1:8051' },
        '^/api(?:/|$)': { target: env.ASTRA_DEV_API_TARGET || 'http://127.0.0.1:8050' },
      },
    },
  }
})
