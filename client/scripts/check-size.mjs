// Bundle budget (design doc 11.10): the main entry ≤ 300 KB gzip. The editor chunk
// and Pyodide are loaded lazily and are not counted.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { gzipSync } from "node:zlib";

const dist = join(process.cwd(), "dist");
const html = readFileSync(join(dist, "index.html"), "utf8");
const entries = [...html.matchAll(/(?:src|href)="\/(assets\/[^"]+\.(?:js|css))"/g)].map((m) => m[1]);
let total = 0;
for (const file of entries) {
  const size = gzipSync(readFileSync(join(dist, file))).length;
  total += size;
  console.log(`${file}: ${(size / 1024).toFixed(1)} KB gzip`);
}
const lazy = readdirSync(join(dist, "assets")).filter((f) => f.endsWith(".js") && !entries.includes(`assets/${f}`));
console.log(`lazy chunks: ${lazy.join(", ")}`);
console.log(`initial total: ${(total / 1024).toFixed(1)} KB gzip (budget 300 KB)`);
if (total > 300 * 1024) {
  console.error("bundle budget exceeded");
  process.exit(1);
}
