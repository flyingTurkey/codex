import { readdir, readFile } from 'node:fs/promises'
import { extname, join, resolve } from 'node:path'

const componentDirectory = resolve(process.cwd(), 'src/components')

async function sourceFiles(directory: string): Promise<string[]> {
  const entries = await readdir(directory, { withFileTypes: true })
  const nestedFiles = await Promise.all(
    entries.map((entry) => {
      const path = join(directory, entry.name)
      return entry.isDirectory() ? sourceFiles(path) : Promise.resolve([path])
    }),
  )

  return nestedFiles.flat().filter((path) => ['.ts', '.vue'].includes(extname(path)))
}

describe('component color guard', () => {
  it('keeps literal six-digit colors out of UI component sources', async () => {
    const violations: string[] = []

    for (const file of await sourceFiles(componentDirectory)) {
      const source = await readFile(file, 'utf8')
      if (/#[0-9A-Fa-f]{6}\b/.test(source)) violations.push(file)
    }

    expect(violations).toEqual([])
  })
})
