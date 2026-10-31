import { spawn } from 'node:child_process'
import process from 'node:process'

process.env.JARVIS_PROVIDER = 'hermes'
const child = spawn(process.execPath, ['bridge/server.mjs'], {
  stdio: 'inherit',
  env: process.env,
})
child.on('exit', (code) => process.exit(code ?? 0))
