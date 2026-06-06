import { defineConfig } from 'vite'

// Slidev 基于 Vite;deck 经 Cloudflare quick tunnel 暴露时,
// Vite 5.4.12+ 会拦截非本地 Host。放行 *.trycloudflare.com 子域。
export default defineConfig({
  server: {
    allowedHosts: ['.trycloudflare.com'],
  },
})
