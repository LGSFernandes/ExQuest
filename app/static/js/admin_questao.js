/* Preview ao vivo do editor de questões. Usa textContent (nunca innerHTML) e o mesmo renderizador KaTeX das telas dos alunos. */
(function () {
  var form = document.querySelector("[data-preview-form]");
  if (!form) return;
  var pvE = document.getElementById("pv-enunciado"), pvA = document.getElementById("pv-alternativas"), pvX = document.getElementById("pv-explicacao");
  function atualizar() {
    pvE.textContent = form.querySelector("[data-preview=enunciado]").value;
    pvX.textContent = form.querySelector("[data-preview=explicacao]").value;
    pvA.textContent = "";
    form.querySelectorAll("input[name=alt_texto]").forEach(function (i) {
      if (!i.value.trim()) return;
      var li = document.createElement("li"), sp = document.createElement("span"); sp.textContent = i.value; li.appendChild(sp); pvA.appendChild(li);
    });
    [pvE, pvA, pvX].forEach(function (el) { if (window.exqKatex) window.exqKatex(el); });
    var multipla = form.querySelector("[name=tipo]").value === "multipla";
    form.querySelector("[data-bloco=multipla]").hidden = !multipla;
    form.querySelector("[data-bloco=discursiva]").hidden = multipla;
  }
  form.addEventListener("input", atualizar); form.addEventListener("change", atualizar);
  // o KaTeX é carregado com defer: espera a página terminar para o primeiro desenho
  window.addEventListener("load", atualizar);
})();
