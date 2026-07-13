import { describe, expect, it } from 'vitest'

interface UuidV7Module {
  createUuidV7: (timestamp?: number, randomBytes?: Uint8Array) => string
}

const uuidModules = import.meta.glob<UuidV7Module>('../app/utils/uuid-v[7].ts', { eager: true })

function getCreateUuidV7(): UuidV7Module['createUuidV7'] | undefined {
  return uuidModules['../app/utils/uuid-v7.ts']?.createUuidV7
}

describe('createUuidV7', () => {
  it('creates an RFC UUID with version 7 and the RFC variant', () => {
    const createUuidV7 = getCreateUuidV7()
    expect(createUuidV7, 'uuid-v7.ts should export createUuidV7').toBeTypeOf('function')
    if (!createUuidV7) return

    const uuid = createUuidV7()

    expect(uuid).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
  })

  it('produces a distinct identifier on repeated calls', () => {
    const createUuidV7 = getCreateUuidV7()
    expect(createUuidV7, 'uuid-v7.ts should export createUuidV7').toBeTypeOf('function')
    if (!createUuidV7) return

    expect(createUuidV7()).not.toBe(createUuidV7())
  })

  it('encodes an injected 48-bit timestamp and random bytes deterministically', () => {
    const createUuidV7 = getCreateUuidV7()
    expect(createUuidV7, 'uuid-v7.ts should export createUuidV7').toBeTypeOf('function')
    if (!createUuidV7) return

    const uuid = createUuidV7(
      0x0123_4567_89ab,
      Uint8Array.from([0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88, 0x99]),
    )

    expect(uuid).toBe('01234567-89ab-7011-a233-445566778899')
  })
})
