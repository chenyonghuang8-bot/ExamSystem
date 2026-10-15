// 把 ../frontend 复制到 www/，并把绝对路径改为相对路径（App 内从本地加载）
const fs = require('fs'), path = require('path');
const src = path.join(__dirname, '..', '..', 'frontend'), out = path.join(__dirname, '..', 'www');
fs.rmSync(out, { recursive: true, force: true }); fs.mkdirSync(out, { recursive: true });
for (const f of fs.readdirSync(src)) if (f !== 'sw.js') fs.copyFileSync(path.join(src, f), path.join(out, f));
const ix = path.join(out, 'index.html');
let h = fs.readFileSync(ix, 'utf8').replace(/(href|src)="\/static\//g, '$1="./').replace(/href="\/manifest/g, 'href="./manifest');
fs.writeFileSync(ix, h);
console.log('web assets copied to www/');
