/* Resposta de questões: envia ao servidor (que corrige) e mostra o resultado. Sem estilos/handlers inline (CSP). */
(function () {
  "use strict";
  var raiz = document.getElementById("questao");
  if (!raiz) return;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var token = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
  var btn = $("[data-enviar]", raiz), gab = $("[data-gabarito]", raiz), texto = $("[data-resposta]", raiz);
  var enviado = false;

  function pronto() { btn.disabled = enviado || (gab ? !$("input:checked", gab) : !texto.value.trim()); }
  if (gab) gab.addEventListener("change", pronto);
  if (texto) texto.addEventListener("input", pronto);

  function sinal(opc, certa) {
    var s = $(".opcao-sinal", opc);
    s.innerHTML = '<svg class="icone" aria-hidden="true"><use href="/static/icons.svg#' + (certa ? "check" : "x") + '"/></svg>';
  }
  function ganho(rotulo) { var t = document.createElement("span"); t.className = "tag"; t.textContent = rotulo; $("#res-ganhos").appendChild(t); }

  btn.addEventListener("click", function () {
    if (enviado) return;
    var corpo = { questao_id: parseInt(raiz.dataset.questao, 10), sessao_id: raiz.dataset.sessao };
    if (gab) corpo.alternativa_id = parseInt($("input:checked", gab).value, 10); else corpo.resposta_texto = texto.value;
    enviado = true; btn.disabled = true; btn.classList.add("btn-carregando");
    fetch(raiz.dataset.url, { method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": token }, body: JSON.stringify(corpo) })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (x) {
        btn.classList.remove("btn-carregando");
        if (!x.ok) { enviado = false; pronto(); mostrarErro(x.d.erro || "Não foi possível enviar. Tente de novo."); return; }
        mostrar(x.d);
      })
      .catch(function () { btn.classList.remove("btn-carregando"); enviado = false; pronto(); mostrarErro("Sem conexão. Sua resposta não foi enviada."); });
  });

  function mostrarErro(msg) {
    var r = $("#resultado"); r.hidden = false; $("#res-titulo").textContent = msg;
    $("#res-feedback").textContent = ""; $("#res-explicacao").hidden = true; $("#proxima").hidden = true; $("#res-ganhos").textContent = "";
  }

  function mostrar(d) {
    var r = $("#resultado"); r.hidden = false; $("#proxima").hidden = false; $("#acoes").hidden = true; $("#res-ganhos").textContent = "";
    $("#res-titulo").textContent = d.acertou ? "Resposta correta" : "Resposta incorreta";
    if (gab) {
      gab.classList.add("corrigido");
      Array.prototype.forEach.call(gab.querySelectorAll(".opcao"), function (o) {
        var id = parseInt(o.dataset.alt, 10), marcada = $("input", o).checked;
        $("input", o).disabled = true;
        if (id === d.alternativa_correta_id) { o.classList.add("certa"); sinal(o, true); }
        else if (marcada) { o.classList.add("errada"); sinal(o, false); }
      });
      $("#res-feedback").textContent = "";
    } else {
      $("#res-feedback").textContent = d.feedback + (d.gabarito ? " Gabarito: " + d.gabarito : "");
      texto.readOnly = true;
    }
    if (d.xp_ganho) ganho("+" + d.xp_ganho + " XP");
    if (d.moedas_ganhas) ganho("+" + d.moedas_ganhas + " moedas");
    if (d.acertou && !d.primeira_vez) $("#res-feedback").textContent = ($("#res-feedback").textContent + " Você já tinha acertado esta questão, então não rende novo XP.").trim();
    if (d.subiu_nivel) ganho("Nível " + d.nivel);
    var exp = $("#res-explicacao");
    if (d.explicacao) { exp.textContent = d.explicacao; exp.hidden = false; if (window.exqKatex) window.exqKatex(); }
    var rest = document.getElementById("restante");
    if (rest && d.limite && d.limite.restante !== null) rest.textContent = d.limite.restante;
    var moedas = document.querySelector(".topo .moeda .num"); if (moedas) moedas.textContent = d.moedas_total;
    r.scrollIntoView({ block: "nearest", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    $("#proxima").focus();
  }
})();

/* Menu "Salvar": liga/desliga a questão nas coleções do aluno. */
(function () {
  var menu = document.querySelector("[data-salvar]");
  if (!menu) return;
  var token = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
  var msg = menu.querySelector("[data-salvar-msg]");
  menu.addEventListener("change", function (e) {
    var cb = e.target; if (cb.type !== "checkbox") return;
    cb.disabled = true; msg.textContent = "";
    fetch(menu.dataset.url, { method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": token },
      body: JSON.stringify({ colecao_id: parseInt(cb.value, 10), presente: cb.checked }) })
      .then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.erro); }); })
      .then(function () { msg.textContent = cb.checked ? "Salva." : "Removida."; })
      .catch(function (err) { cb.checked = !cb.checked; msg.textContent = err.message || "Não foi possível salvar."; })
      .then(function () { cb.disabled = false; });
  });
})();
