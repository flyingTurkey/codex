import { readdirSync, readFileSync, statSync } from 'node:fs'
import { extname, join, relative, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const appRoot = resolve(process.cwd(), 'app')
const guardedExtensions = new Set(['.css', '.ts', '.vue'])
const hexColor = /#[\da-fA-F]{3,4}(?:[\da-fA-F]{2}){0,2}\b/g

function productionFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry)
    return statSync(path).isDirectory()
      ? productionFiles(path)
      : guardedExtensions.has(extname(path))
        ? [path]
        : []
  })
}

describe('apps/web token guard', () => {
  it('contains no scattered hexadecimal colors in production app sources', () => {
    const violations = productionFiles(appRoot).flatMap((path) => {
      const matches = readFileSync(path, 'utf8').match(hexColor) ?? []
      return matches.map((color) => `${relative(appRoot, path)}: ${color}`)
    })

    expect(violations).toEqual([])
  })
})
