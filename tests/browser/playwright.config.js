const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
  testDir: '.', testMatch: '*.spec.js', timeout: 60000, workers: 1,
  reporter: [['list'], ['json', { outputFile: '../../build/browser-results.json' }]],
  use: {
    baseURL: process.env.LAB_URL || 'http://127.0.0.1:18088',
    headless: true,
    launchOptions: { executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome', args: ['--no-sandbox'] },
    trace: 'off', screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'UTC', use: { timezoneId: 'UTC' } },
    { name: 'Tehran', use: { timezoneId: 'Asia/Tehran' } },
  ],
});
