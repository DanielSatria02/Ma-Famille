import { defineConfig } from 'vitest/config'

// Pure-logic tests only for now: the date and booking rules carry the traps
// worth pinning down (a UTC shift in a date helper, an off-by-one in an hour
// range) and need no DOM.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.js'],
  },
})
