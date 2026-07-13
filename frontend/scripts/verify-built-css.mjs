import { readdir, readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const assets = resolve('dist/assets')
const cssFiles = (await readdir(assets)).filter((name) => name.endsWith('.css'))

if (cssFiles.length === 0) throw new Error('No se genero CSS en dist/assets')

for (const name of cssFiles) {
  const css = await readFile(resolve(assets, name), 'utf8')
  if (/@tailwind\b|@apply\b/.test(css)) {
    throw new Error(`${name} contiene Tailwind sin procesar`)
  }
  if (!css.includes('.fg-btn-primary')) {
    throw new Error(`${name} no contiene componentes FGPY`)
  }
}
