const fs = require('fs');
const path = require('path');

const targetFiles = [
  'node_modules/html2canvas/dist/html2canvas.js',
  'node_modules/html2canvas/dist/html2canvas.esm.js',
  'node_modules/html2canvas/dist/lib/css/types/color.js'
];

targetFiles.forEach((relPath) => {
  const fullPath = path.resolve(__dirname, '..', relPath);
  if (fs.existsSync(fullPath)) {
    let content = fs.readFileSync(fullPath, 'utf8');
    const searchTarget = /throw new Error\("Attempting to parse an unsupported color function \\"" \+ value\.name \+ "\\""\);/g;
    if (searchTarget.test(content)) {
      content = content.replace(searchTarget, 'return 0;');
      fs.writeFileSync(fullPath, content, 'utf8');
      console.log(`[patch-html2canvas] Successfully patched ${relPath}`);
    } else {
      console.log(`[patch-html2canvas] Already patched or pattern not found in ${relPath}`);
    }
  }
});
