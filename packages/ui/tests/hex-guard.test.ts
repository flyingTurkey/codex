import { readdir, readFile } from 'node:fs/promises'
import { extname, join, resolve } from 'node:path'

const componentDirectory = resolve(process.cwd(), 'src/components')
const hexColorLiteral = /#(?:[0-9A-Fa-f]{8}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{4}|[0-9A-Fa-f]{3})(?![0-9A-Fa-f])/

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
  it.each(['#abc', '#abcd', '#aabbcc', '#aabbccdd'])(
    'detects the supported CSS hex literal %s',
    (literal) => {
      expect(hexColorLiteral.test(literal)).toBe(true)
    },
  )

  it.each(['#ab', '#abcde', '#aabbccd', '#aabbccddee'])(
    'does not treat the unsupported hex length %s as a color',
    (literal) => {
      expect(hexColorLiteral.test(literal)).toBe(false)
    },
  )

  it('keeps CSS hex color literals out of UI component sources', async () => {
    const violations: string[] = []

    for (const file of await sourceFiles(componentDirectory)) {
      const source = await readFile(file, 'utf8')
      if (hexColorLiteral.test(source)) violations.push(file)
    }

    expect(violations).toEqual([])
  })
})
