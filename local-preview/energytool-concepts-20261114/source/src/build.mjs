// Сборка HTML-экранов: node src/build.mjs [фильтр]
import fs from 'node:fs';
import path from 'node:path';
import { page } from './lib.mjs';
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const filter = process.argv[2] || '';
const mods = fs.readdirSync(path.join(root, 'src')).filter(f => /^(c\d\d|s\d|b\d\d).*\.mjs$/.test(f)).sort();
const index = [];
for (const m of mods) {
  const { screens } = await import(path.join(root, 'src', m) + '?v=' + Date.now());
  for (const s of screens) {
    index.push({ id: s.id, concept: s.concept, title: s.title, w: s.w || 1440, h: s.h || 960, mobile: !!s.mobile, group: s.group || '' });
    if (filter && !s.id.includes(filter)) continue;
    fs.writeFileSync(path.join(root, 'html', s.id + '.html'), page({ w: 1440, h: 960, ...s }));
  }
}
fs.writeFileSync(path.join(root, 'tmp', 'index.json'), JSON.stringify(index, null, 1));
console.log('built', index.filter(s => !filter || s.id.includes(filter)).length, 'of', index.length);
