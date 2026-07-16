// Purpose: configure extension source linting. Responsibilities: apply TypeScript-safe defaults while ignoring generated bundles. Future modules: add targeted rules after real extension behavior exists.
import eslint from '@eslint/js';
import tseslint from 'typescript-eslint';

export default tseslint.config(eslint.configs.recommended, ...tseslint.configs.recommended, {
  ignores: ['.plasmo/**', 'build/**', 'dist/**'],
});
