const fs = require('fs');
const path = require('path');

const directoryPath = path.join(__dirname, 'src');

const replacements = [
  { regex: /border-2 border-black/g, replacement: 'border border-gray-200' },
  { regex: /border-b-2 border-black/g, replacement: 'border-b border-gray-200' },
  { regex: /border-t-2 border-black/g, replacement: 'border-t border-gray-200' },
  { regex: /border-l-2 border-black/g, replacement: 'border-l border-gray-200' },
  { regex: /border-r-2 border-black/g, replacement: 'border-r border-gray-200' },
  { regex: /border border-black/g, replacement: 'border border-gray-200' },
  { regex: /shadow-\[.*?rgba\(0,0,0,1\)\]/g, replacement: 'shadow-sm rounded-lg' },
  { regex: /bg-\[#f4f4f0\]/g, replacement: 'bg-[#f3f4f6]' },
  { regex: /bg-\[#00ff4c\]/g, replacement: 'bg-blue-600 text-white' },
  { regex: /text-black/g, replacement: 'text-gray-900' },
  { regex: /hover:border-black/g, replacement: 'hover:border-gray-400' },
  { regex: /hover:bg-\[#00e676\]/g, replacement: 'hover:bg-blue-700' },
  { regex: /hover:bg-black/g, replacement: 'hover:bg-gray-100 hover:text-gray-900' },
  { regex: /hover:text-\[#00ff4c\]/g, replacement: '' }
];

function replaceInFile(filePath) {
  let content = fs.readFileSync(filePath, 'utf8');
  let newContent = content;
  
  for (const {regex, replacement} of replacements) {
    newContent = newContent.replace(regex, replacement);
  }
  
  if (content !== newContent) {
    fs.writeFileSync(filePath, newContent, 'utf8');
    console.log(`Updated ${filePath}`);
  }
}

function walkDir(dir) {
  const files = fs.readdirSync(dir);
  for (const file of files) {
    const fullPath = path.join(dir, file);
    if (fs.statSync(fullPath).isDirectory()) {
      walkDir(fullPath);
    } else if (fullPath.endsWith('.jsx')) {
      replaceInFile(fullPath);
    }
  }
}

walkDir(directoryPath);
console.log("Done.");
