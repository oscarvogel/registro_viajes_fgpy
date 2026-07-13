import assert from 'node:assert/strict'
import { readdir, readFile } from 'node:fs/promises'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const sourceRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../src')
const mojibake = /Ã|Â|â[\u0080-\u00ff€]|ð|ï¿½|�/u

const sourceFiles = async (directory) => {
  const entries = await readdir(directory, { withFileTypes: true })
  const nested = await Promise.all(entries.map((entry) => {
    const target = path.join(directory, entry.name)
    return entry.isDirectory() ? sourceFiles(target) : [target]
  }))
  return nested.flat().filter((file) => /\.(?:js|vue)$/u.test(file))
}

test('frontend source does not contain UTF-8 mojibake', async () => {
  const affected = []
  for (const file of await sourceFiles(sourceRoot)) {
    const lines = (await readFile(file, 'utf8')).split(/\r?\n/u)
    lines.forEach((line, index) => {
      if (mojibake.test(line)) affected.push(`${path.relative(sourceRoot, file)}:${index + 1}`)
    })
  }
  assert.deepEqual(affected, [], `Texto UTF-8 dañado en:\n${affected.join('\n')}`)
})
