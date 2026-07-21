// Purpose: configure frontend linting. Responsibilities: apply TypeScript-safe defaults while excluding build output. Future modules: add narrow rules when a recurring defect justifies them.
import eslint from '@eslint/js';
import tseslint from 'typescript-eslint';

export default tseslint.config(eslint.configs.recommended, ...tseslint.configs.recommended, {
  // '.next-judge/**' is the second dev server's build output (see distDir in next.config.ts).
  ignores: ['.next/**', '.next-judge/**', 'coverage/**', 'next-env.d.ts'],
});
