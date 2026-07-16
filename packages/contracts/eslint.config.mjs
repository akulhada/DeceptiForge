// Purpose: lint shared TypeScript contracts. Responsibilities: enforce conservative syntax checks without framework assumptions. Future modules: add contract-specific checks only after a recurring defect.
import eslint from '@eslint/js';
import tseslint from 'typescript-eslint';

export default tseslint.config(eslint.configs.recommended, ...tseslint.configs.recommended);
