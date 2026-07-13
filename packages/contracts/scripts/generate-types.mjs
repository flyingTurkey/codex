import { readdir, mkdir, rm, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { compileFromFile } from 'json-schema-to-typescript'

const packageRoot = join(dirname(fileURLToPath(import.meta.url)), '..')
const schemaDir = join(packageRoot, 'generated', 'json-schema')
const outputPath = join(packageRoot, 'generated', 'types', 'index.d.ts')
const schemaFiles = (await readdir(schemaDir))
  .filter((file) => file.endsWith('.json'))
  .sort()

const publicExports = {
  'cursor-page.schema.json': ['CursorPageDictStrUnionStrIntBoolNoneType'],
  'liveness-response.schema.json': ['LivenessResponse'],
  'problem-details.schema.json': ['ProblemDetails'],
  'readiness-response.schema.json': ['DependencyCheck', 'ReadinessResponse'],
  'version-response.schema.json': ['VersionResponse'],
}

await mkdir(dirname(outputPath), { recursive: true })
const staleDeclarations = (await readdir(dirname(outputPath)))
  .filter((file) => file.endsWith('.d.ts'))
for (const staleDeclaration of staleDeclarations) {
  await rm(join(dirname(outputPath), staleDeclaration))
}

const reexports = []
for (const schemaFile of schemaFiles) {
  const outputFile = schemaFile.replace(/\.json$/, '.d.ts')
  const declaration = await compileFromFile(join(schemaDir, schemaFile), {
    bannerComment: '',
    style: { semi: false, singleQuote: true },
    unknownAny: false,
  })
  await writeFile(join(dirname(outputPath), outputFile), declaration, 'utf8')
  const exportedNames = publicExports[schemaFile]
  if (!exportedNames) {
    throw new Error(`No public export mapping for ${schemaFile}`)
  }
  for (const exportedName of exportedNames) {
    reexports.push(
      `export type { ${exportedName} } from './${outputFile.replace(/\.d\.ts$/, '')}'`,
    )
  }
}

const banner = '// Generated from canonical Pydantic contracts. Do not edit directly.\n\n'
await writeFile(outputPath, banner + reexports.join('\n') + '\n', 'utf8')
