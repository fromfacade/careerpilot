/// <reference types="vitest/config" />
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

const tokenFile = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../backend/storage/local-api-token')

function careerPilotToken(): Plugin {
  return {
    name: 'careerpilot-local-token',
    resolveId(id) {
      if (id === 'virtual:careerpilot-token') return '\0careerpilot-token'
    },
    load(id) {
      if (id !== '\0careerpilot-token') return
      let token = ''
      try {
        token = fs.readFileSync(tokenFile, 'utf8').trim()
      } catch {
        token = ''
      }
      return `export default ${JSON.stringify(token)}`
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss(), careerPilotToken()],
  server: {
    port: 5173,
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
  },
})
