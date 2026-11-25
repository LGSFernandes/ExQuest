/* KaTeX sob demanda: o JS/CSS/fontes (~300 KB) só são baixados quando a página tem fórmula.
   Renderiza ($...$, $$...$$, \(...\), \[...\]) dentro de [data-katex]. window.exqKatex(raiz?) renderiza só dentro de `raiz`
   (conteúdo inserido depois, como o preview do admin e o chat). URLs versionadas vêm dos data-* da tag <script>. */
(function () {
  var tag = document.currentScript, U = tag ? tag.dataset : {};
  var OPCOES = {
    delimiters: [{ left: "$$", right: "$$", display: true }, { left: "\\[", right: "\\]", display: true },
                 { left: "$", right: "$", display: false }, { left: "\\(", right: "\\)", display: false }],
    throwOnError: false, strict: "ignore",
    // limites contra fórmulas hostis (macro em laço, tamanhos enormes): o conteúdo vem de usuários
    maxExpand: 1000, maxSize: 20, trust: false
  };
  var carga = null;
  function script(src) {
    return new Promise(function (ok, falha) {
      var s = document.createElement("script"); s.src = src; s.onload = ok; s.onerror = falha; document.head.appendChild(s);
    });
  }
  function carregar() {
    if (window.renderMathInElement) return Promise.resolve();
    if (!carga && U.js) {
      var l = document.createElement("link"); l.rel = "stylesheet"; l.href = U.css; document.head.appendChild(l);
      carga = script(U.js).then(function () { return script(U.auto); });
    }
    return carga || Promise.reject();
  }
  function temFormula(el) { return /\$|\\\(|\\\[/.test(el.textContent || ""); }
  function renderizar(raiz) {
    var alvo = raiz && raiz.nodeType === 1 ? [raiz] : Array.prototype.slice.call(document.querySelectorAll("[data-katex]"));
    alvo = alvo.filter(temFormula);
    if (!alvo.length) return;
    carregar().then(function () {
      alvo.forEach(function (el) { window.renderMathInElement(el, OPCOES); });
    }).catch(function () { /* sem rede: o texto da fórmula continua legível */ });
  }
  window.exqKatex = renderizar;
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { renderizar(); }); else renderizar();
})();
