// Purpose: configure extension unit tests. Responsibilities: discover deterministic TypeScript tests without browser automation. Future modules: add browser integration testing when extension interactions exist.
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'node',
    include: ['test/**/*.test.ts'],
  },
});
