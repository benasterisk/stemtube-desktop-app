// Tauri embeds ../dist, which is gitignored and was never refreshed: release
// builds shipped a months-old splash without the running/quit control panel.
// Run as beforeBuildCommand so dist always mirrors src-tauri/splash.html.
const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');
fs.mkdirSync(path.join(root, 'dist'), { recursive: true });
fs.copyFileSync(path.join(root, 'src-tauri', 'splash.html'), path.join(root, 'dist', 'splash.html'));
console.log('dist/splash.html synced');
