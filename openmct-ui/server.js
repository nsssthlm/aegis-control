const express = require('express');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 8080;

// Serve static files from the root directory
app.use(express.static(path.join(__dirname), {
  extensions: ['html', 'js', 'css'],
  index: 'index.html'
}));

// Serve plugin files
app.use('/plugins', express.static(path.join(__dirname, 'plugins')));

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({
    status: 'NOMINAL',
    service: 'aegis-control-openmct-ui',
    version: '4.0.0',
    uptime: process.uptime(),
    timestamp: new Date().toISOString()
  });
});

// Fallback to index.html for SPA-style routing
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'index.html'));
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`
  ╔══════════════════════════════════════════════╗
  ║         AEGIS CONTROL — UI SERVER            ║
  ║══════════════════════════════════════════════║
  ║  STATUS:  ONLINE                             ║
  ║  PORT:    ${String(PORT).padEnd(37)}║
  ║  MODE:    ${(process.env.NODE_ENV || 'development').padEnd(37)}║
  ╚══════════════════════════════════════════════╝
  `);
});
