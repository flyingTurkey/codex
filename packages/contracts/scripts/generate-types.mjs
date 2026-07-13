import { readdir, mkdir, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { compileFromFile } from 'json-schema-to-typescript'

const packageRoot = join(dirname(fileURLToPath(import.meta.url)), '..')
const schemaDir = join(packageRoot, 'generated', 'json-schema')
const outputPath = join(packageRoot, 'generated', 'types', 'index.d.ts')
const schemaFiles = (await readdir(schemaDir))
  .filter((file) => file.endsWith('.json'))
  .sort()

const declarations = []
for (const schemaFile of schemaFiles) {
  declarations.push(
    await compileFromFile(join(schemaDir, schemaFile), {
      bannerComment: '',
      style: { semi: false, singleQuote: true },
      unknownAny: false,
    }),
  )
}

const banner = '// Generated from canonical Pydantic contracts. Do not edit directly.\n\n'
await mkdir(dirname(outputPath), { recursive: true })
await writeFile(outputPath, banner + declarations.join('\n'), 'utf8')
