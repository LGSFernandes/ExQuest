// Gera app/static/icons.svg (sprite) a partir de tools/icones.txt usando Lucide (licença ISC).
// Uso: node tools/gerar_sprite.mjs <pasta com node_modules/lucide-static>
import fs from "node:fs";
import path from "node:path";

const base = path.resolve(process.argv[2] || ".");
const dir = path.join(base, "node_modules/lucide-static/icons");
const nomes = fs.readFileSync(new URL("./icones.txt", import.meta.url), "utf8").split("\n").map(s => s.trim()).filter(Boolean);
const faltam = [], simbolos = [];
for (const n of [...new Set(nomes)]) {
  const f = path.join(dir, `${n}.svg`);
  if (!fs.existsSync(f)) { faltam.push(n); continue; }
  const interno = fs.readFileSync(f, "utf8").replace(/^[\s\S]*?<svg[^>]*>/, "").replace(/<\/svg>\s*$/, "").replace(/\s+/g, " ").trim();
  simbolos.push(`<symbol id="${n}" viewBox="0 0 24 24">${interno}</symbol>`);
}
if (faltam.length) { console.error("Ícones inexistentes na versão instalada:", faltam.join(", ")); process.exit(1); }
const out = `<svg xmlns="http://www.w3.org/2000/svg" style="display:none">\n<!-- Lucide (ISC) — gerado por tools/gerar_sprite.mjs; não editar à mão -->\n${simbolos.join("\n")}\n</svg>\n`;
fs.writeFileSync(new URL("../app/static/icons.svg", import.meta.url), out);
console.log(`${simbolos.length} ícones gravados`);
