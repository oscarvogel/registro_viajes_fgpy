import { writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const pad = (n) => String(n).padStart(2, '0');
const now = new Date();
const version = `${now.getFullYear()}.${pad(now.getMonth() + 1)}.${pad(now.getDate())}.${pad(now.getHours())}${pad(now.getMinutes())}`;

const envProdPath = resolve(process.cwd(), '.env.production');
const envLocalPath = resolve(process.cwd(), '.env.local');

writeFileSync(envProdPath, `VITE_APP_VERSION=${version}\n`, 'utf8');
writeFileSync(envLocalPath, `VITE_APP_VERSION=${version}\n`, 'utf8');

console.log(`VITE_APP_VERSION set to ${version}`);
