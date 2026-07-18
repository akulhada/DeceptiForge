// Purpose: configure frontend unit tests. Responsibilities: discover deterministic TypeScript tests without a browser harness. Future modules: add browser testing only when component behavior exists.
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'node',
    include: ['test/**/*.test.ts', 'services/**/*.test.ts'],
  },
});
