const fs = require('fs');
const path = require('path');

function walkAndPatch(dir) {
  if (!fs.existsSync(dir)) return;
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walkAndPatch(fullPath);
    } else if (entry.name.endsWith('.js') || entry.name.endsWith('.mjs')) {
      try {
        let content = fs.readFileSync(fullPath, 'utf8');
        if (content.includes('unsupported color function')) {
          console.log(`[patch-html2canvas] Found unsupported color error in: ${fullPath}`);
          // Replace throw statement with return 0
          const patched = content.replace(
            /throw\s+(?:new\s+)?Error\(['"]Attempting to parse an unsupported color function[\s\S]*?\);?/g,
            'return 0;'
          );
          if (patched !== content) {
            fs.writeFileSync(fullPath, patched, 'utf8');
            console.log(`[patch-html2canvas] Successfully patched ${fullPath}`);
          }
        }
      } catch (err) {
        console.error(`[patch-html2canvas] Error reading/patching ${fullPath}:`, err.message);
      }
    }
  }
}

const html2canvasDir = path.resolve(__dirname, '..', 'node_modules', 'html2canvas');
if (fs.existsSync(html2canvasDir)) {
  console.log('[patch-html2canvas] Scanning node_modules/html2canvas for unsupported color functions...');
  walkAndPatch(html2canvasDir);
  console.log('[patch-html2canvas] Done.');
} else {
  console.log('[patch-html2canvas] node_modules/html2canvas not found.');
}
