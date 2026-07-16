// Purpose: establish root ESLint ignore policy. Responsibilities: prevent linting generated and non-JavaScript artifacts. Future modules: application rules remain in each app configuration.
export default [
  {
    ignores: ['**/node_modules/**', '**/.next/**', '**/dist/**', '**/.plasmo/**', '**/coverage/**'],
  },
];
