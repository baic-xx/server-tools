import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd() + '/..', '')
  return {
    plugins: [vue()],
    server: {
      port: parseInt(env.FRONTEND_PORT || '30251'),
      proxy: {
        '/api': {
          target: `http://localhost:${env.BACKEND_PORT || '30252'}`,
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: '../server/static',
      emptyOutDir: true,
    },
  }
})
