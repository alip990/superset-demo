import { defineConfig } from 'vitest/config';
import path from 'node:path';
const harness = path.resolve(__dirname, 'tests/hostHarness.tsx');
export default defineConfig({
  test: { environment: 'jsdom', include: ['tests/*.spec.tsx'], globals: true },
  esbuild: { jsx: 'automatic' },
  resolve: { alias: [
    { find: /^@superset-ui\/core\/components$/, replacement: harness },
    { find: /^@superset-ui\/core\/utils\/dates$/, replacement: harness },
    { find: /^@apache-superset\/core\/(theme|translation)$/, replacement: harness },
    { find: 'src/utils/getBootstrapData', replacement: path.resolve(__dirname, 'tests/bootstrapHarness.ts') },
  ] },
});
