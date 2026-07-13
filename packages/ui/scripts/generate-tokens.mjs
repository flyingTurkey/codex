import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const packageDirectory = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const tokenSourcePath = resolve(packageDirectory, '../../docs/codex-kit/assets/ui/design_tokens.json')
const generatedDirectory = resolve(packageDirectory, 'src/generated')
const checkOnly = process.argv.includes('--check')

const paletteSteps = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950]
const nuxtUiRoles = {
  primary: 'brand',
  neutral: 'ink',
  success: 'verified',
  info: 'digital',
  warning: 'reviewPending',
  error: 'conflict',
}

function leafPaths(value, prefix = '') {
  return Object.entries(value).flatMap(([key, child]) => {
    const path = prefix ? `${prefix}.${key}` : key
    return child !== null && typeof child === 'object' ? leafPaths(child, path) : [path]
  })
}

function cssName(value) {
  return value.replaceAll(/([a-z0-9])([A-Z])/g, '$1-$2').toLowerCase()
}

function flatten(value, prefix = '', normalizeNames = true) {
  return Object.entries(value).flatMap(([key, child]) => {
    const segment = normalizeNames ? cssName(key) : key
    const path = prefix ? `${prefix}-${segment}` : segment
    return child !== null && typeof child === 'object'
      ? flatten(child, path, normalizeNames)
      : [[path, String(child)]]
  })
}

function nearestExistingStep(availableSteps, requestedStep) {
  return availableSteps.reduce((nearest, candidate) => {
    const distance = Math.abs(candidate - requestedStep)
    const nearestDistance = Math.abs(nearest - requestedStep)
    return distance < nearestDistance ? candidate : nearest
  })
}

function generateTypeScript(tokens) {
  const paths = leafPaths(tokens)
    .map((path) => `  | ${JSON.stringify(path)}`)
    .join('\n')
  const serializedTokens = JSON.stringify(tokens, null, 2)
  const serializedRoles = JSON.stringify({ ui: { colors: nuxtUiRoles } }, null, 2)

  return `// Generated from docs/codex-kit/assets/ui/design_tokens.json. Do not edit.\n` +
    `function deepFreeze<const T extends object>(value: T): Readonly<T> {\n` +
    `  for (const child of Object.values(value)) {\n` +
    `    if (child !== null && typeof child === 'object') deepFreeze(child as object)\n` +
    `  }\n` +
    `  return Object.freeze(value)\n` +
    `}\n\n` +
    `export const designTokens = deepFreeze(${serializedTokens} as const)\n\n` +
    `export type DesignTokens = typeof designTokens\n\n` +
    `export type TokenPath =\n${paths}\n\n` +
    `export const nuxtUiAppConfig = ${serializedRoles} as const\n`
}

function generateThemeCss(tokens) {
  const cssTokenGroups = ['color', 'font', 'space', 'radius', 'shadow', 'layout', 'breakpoint', 'motion', 'icon']
  const canonicalVariables = cssTokenGroups
    .flatMap((group) => flatten(tokens[group], group, group !== 'color'))
    .map(([path, value]) => `  --srbg-${path}: ${value};`)
    .join('\n')

  const colorThemeVariables = []
  for (const [name, value] of Object.entries(tokens.color)) {
    if (value !== null && typeof value === 'object') {
      const availableSteps = Object.keys(value).map(Number).sort((left, right) => left - right)
      for (const step of paletteSteps) {
        const sourceStep = nearestExistingStep(availableSteps, step)
        colorThemeVariables.push(
          `  --color-${name}-${step}: var(--srbg-color-${name}-${sourceStep});`,
        )
      }
    } else {
      colorThemeVariables.push(`  --color-${name}: var(--srbg-color-${name});`)
    }
  }

  const typography = [
    `  --font-sans: var(--srbg-font-sans);`,
    `  --font-mono: var(--srbg-font-mono);`,
    ...Object.keys(tokens.font.size).map(
      (name) => `  --text-${name}: var(--srbg-font-size-${cssName(name)});`,
    ),
    ...Object.keys(tokens.font.weight).map(
      (name) => `  --font-weight-${name}: var(--srbg-font-weight-${cssName(name)});`,
    ),
  ]
  const spacing = Object.keys(tokens.space).map(
    (name) => `  --spacing-${name}: var(--srbg-space-${name});`,
  )
  const radii = Object.keys(tokens.radius).map(
    (name) => `  --radius-${name}: var(--srbg-radius-${cssName(name)});`,
  )
  const shadows = Object.keys(tokens.shadow).map(
    (name) => `  --shadow-${name}: var(--srbg-shadow-${cssName(name)});`,
  )
  const breakpoints = Object.keys(tokens.breakpoint).map(
    (name) => `  --breakpoint-${name}: var(--srbg-breakpoint-${cssName(name)});`,
  )

  return `/* Generated from docs/codex-kit/assets/ui/design_tokens.json. Do not edit. */\n` +
    `:root {\n${canonicalVariables}\n}\n\n` +
    `@theme {\n${[...colorThemeVariables, ...typography, ...spacing, ...radii, ...shadows, ...breakpoints].join('\n')}\n}\n`
}

async function expectedOutputs() {
  const source = await readFile(tokenSourcePath, 'utf8')
  const tokens = JSON.parse(source)
  return new Map([
    [resolve(generatedDirectory, 'design-tokens.ts'), generateTypeScript(tokens)],
    [resolve(generatedDirectory, 'theme.css'), generateThemeCss(tokens)],
  ])
}

async function run() {
  const outputs = await expectedOutputs()
  if (checkOnly) {
    const drifted = []
    for (const [path, expected] of outputs) {
      const actual = await readFile(path, 'utf8').catch(() => '')
      if (actual !== expected) drifted.push(path)
    }
    if (drifted.length > 0) {
      throw new Error(`Generated token files are stale: ${drifted.join(', ')}`)
    }
    console.log('Token outputs match design_tokens.json.')
    return
  }

  await mkdir(generatedDirectory, { recursive: true })
  for (const [path, output] of outputs) await writeFile(path, output, 'utf8')
  console.log('Generated type-safe tokens and Tailwind theme CSS.')
}

await run()
