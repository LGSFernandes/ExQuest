/* ExQuest — comportamento global. Sem estilos/handlers inline (CSP estrita). */
(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  /* valores dinâmicos de estilo vindos do servidor: data-vars="--cor:#c6f135;--w:40%" (CSSOM não é bloqueado pela CSP) */
  function aplicarVars(raiz) {
    $$("[data-vars]", raiz).forEach(function (el) {
      el.getAttribute("data-vars").split(";").forEach(function (par) {
        var i = par.indexOf(":");
        if (i > 0) el.style.setProperty(par.slice(0, i).trim(), par.slice(i + 1).trim());
      });
      el.removeAttribute("data-vars");
    });
  }
  window.exqAplicarVars = aplicarVars;

  /* tema */
  function definirTema(t) {
    var h = document.documentElement;
    try {
      if (t === "auto") { h.removeAttribute("data-theme"); localStorage.removeItem("exq-tema"); }
      else { h.setAttribute("data-theme", t); localStorage.setItem("exq-tema", t); }
    } catch (e) { if (t !== "auto") h.setAttribute("data-theme", t); }
    $$("[data-tema]").forEach(function (b) { b.setAttribute("aria-pressed", String(b.getAttribute("data-tema") === t)); });
  }

  document.addEventListener("click", function (e) {
    var alvo = e.target.closest("[data-tema]");
    if (alvo) { definirTema(alvo.getAttribute("data-tema")); return; }

    var abrir = e.target.closest("[data-abrir]");
    if (abrir) { var d = $(abrir.getAttribute("data-abrir")); if (d && d.showModal) d.showModal(); return; }
    var fechar = e.target.closest("[data-fechar]");
    if (fechar) { var dlg = fechar.closest("dialog"); if (dlg) dlg.close(); return; }
    if (e.target.tagName === "DIALOG") e.target.close(); // clique no fundo

    if (e.target.closest("[data-voltar]")) { history.length > 1 ? history.back() : (location.href = "/"); return; }
    var aviso = e.target.closest("[data-dispensar]");
    if (aviso) { var a = aviso.closest(".aviso"); if (a) a.remove(); return; }

    var copiar = e.target.closest("[data-copiar]");
    if (copiar && navigator.clipboard) {
      navigator.clipboard.writeText(copiar.getAttribute("data-copiar")).then(function () {
        var antes = copiar.textContent; copiar.textContent = "Copiado"; setTimeout(function () { copiar.textContent = antes; }, 1600);
      });
      return;
    }
    // fecha menus <details> ao clicar fora
    $$("details.menu[open]").forEach(function (m) { if (!m.contains(e.target)) m.open = false; });
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") $$("details.menu[open]").forEach(function (m) { m.open = false; });
  });

  /* confirmação antes de ações destrutivas: data-confirmar="Texto" em <form> ou <button type=submit> */
  var pendente = null;
  /* ação otimista: <form data-otimista data-otimista-alvo=".nao-lida" data-otimista-classe="nao-lida" data-otimista-ocultar=".sino-num">
     a tela muda na hora e é desfeita se o servidor recusar. O servidor responde 204 a `Accept: application/json`. */
  function otimista(e, f) {
    e.preventDefault();
    if (f.dataset.enviando) return;
    f.dataset.enviando = "1";
    var classe = f.getAttribute("data-otimista-classe"), alvos = $$(f.getAttribute("data-otimista-alvo") || "[hidden]"), ocultar = $$(f.getAttribute("data-otimista-ocultar") || "[hidden]");
    var tinham = alvos.filter(function (el) { return el.classList.contains(classe); }), visiveis = ocultar.filter(function (el) { return !el.hidden; });
    tinham.forEach(function (el) { el.classList.remove(classe); }); visiveis.forEach(function (el) { el.hidden = true; }); f.hidden = true;
    fetch(f.action, { method: "POST", credentials: "same-origin", headers: { Accept: "application/json" }, body: new FormData(f) })
      .then(function (r) { if (!r.ok) throw new Error(); })
      .catch(function () {
        tinham.forEach(function (el) { el.classList.add(classe); }); visiveis.forEach(function (el) { el.hidden = false; }); f.hidden = false;
        var a = document.createElement("p"); a.className = "erro-campo"; a.setAttribute("role", "alert"); a.textContent = "Não foi possível concluir. Tente novamente.";
        f.parentNode.insertBefore(a, f.nextSibling); setTimeout(function () { a.remove(); }, 5000);
      })
      .then(function () { delete f.dataset.enviando; });
  }

  document.addEventListener("submit", function (e) {
    if (e.target.hasAttribute("data-otimista")) { otimista(e, e.target); return; }
    var f = e.target, b = e.submitter, msg = (b && b.getAttribute("data-confirmar")) || f.getAttribute("data-confirmar");
    var modal = $("#dlg-confirmar");
    if (msg && modal && !f.dataset.confirmado) {
      e.preventDefault();
      pendente = { form: f, botao: b };
      $("#dlg-confirmar-texto", modal).textContent = msg;
      modal.showModal();
      return;
    }
    // trava duplo clique
    if (!f.hasAttribute("data-sem-trava")) {
      if (f.dataset.enviando) { e.preventDefault(); return; }
      f.dataset.enviando = "1";
      var s = b || $('button[type="submit"], input[type="submit"]', f);
      if (s) { s.classList.add("btn-carregando"); s.setAttribute("aria-busy", "true"); }
      setTimeout(function () { delete f.dataset.enviando; if (s) { s.classList.remove("btn-carregando"); s.removeAttribute("aria-busy"); } }, 15000);
    }
  });
  var ok = document.getElementById("dlg-confirmar-ok");
  if (ok) ok.addEventListener("click", function () {
    var m = $("#dlg-confirmar"); m.close();
    if (pendente) { pendente.form.dataset.confirmado = "1"; if (pendente.form.requestSubmit) pendente.form.requestSubmit(pendente.botao || undefined); else pendente.form.submit(); }
  });

  /* barra de XP: entra uma vez ao carregar a página */
  function animarReguas() {
    $$("progress[data-anima]").forEach(function (p) {
      var alvo = p.getAttribute("value"); p.value = 0;
      requestAnimationFrame(function () { requestAnimationFrame(function () { p.value = alvo; }); });
    });
    $$("[data-conta]").forEach(function (el) {
      var fim = parseInt(el.getAttribute("data-conta"), 10); if (isNaN(fim)) return;
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { el.textContent = fim.toLocaleString("pt-BR"); return; }
      var t0 = null, dur = 900;
      function passo(t) { if (t0 === null) t0 = t; var k = Math.min(1, (t - t0) / dur); el.textContent = Math.round(fim * (1 - Math.pow(1 - k, 3))).toLocaleString("pt-BR"); if (k < 1) requestAnimationFrame(passo); }
      requestAnimationFrame(passo);
    });
  }

  document.addEventListener("change", function (e) {
    var el = e.target.closest("[data-auto-enviar]");
    if (el && el.form) el.form.requestSubmit();
  });

  /* prévia de imagem antes do envio: <input type=file data-previa="#img"> */
  document.addEventListener("change", function (e) {
    var inp = e.target.closest("input[type=file][data-previa]");
    if (!inp || !inp.files || !inp.files[0]) return;
    var img = $(inp.getAttribute("data-previa")); if (!img) return;
    img.src = URL.createObjectURL(inp.files[0]); img.hidden = false;
  });

  /* avisos somem sozinhos (exceto erros) */
  function iniciarAvisos() {
    $$(".aviso").forEach(function (a) {
      if (a.classList.contains("aviso-erro") || a.classList.contains("aviso-perigo")) return;
      setTimeout(function () { a.style.opacity = "0"; a.style.transition = "opacity .3s"; setTimeout(function () { a.remove(); }, 320); }, 6000);
    });
  }

  /* ── rede: sem chamadas duplicadas e sem respostas velhas ───────────────────────────────────────────
     debounce(fn, ms): agrupa rajadas (digitação) numa única chamada.
     exq.pegar(url, tipo): GETs idênticos em andamento compartilham a mesma requisição.
     exq.ultima(chave, url, tipo): cancela a requisição anterior da mesma chave (a resposta velha nunca sobrescreve a nova). */
  function debounce(fn, ms) { var t; return function () { var a = arguments, c = this; clearTimeout(t); t = setTimeout(function () { fn.apply(c, a); }, ms); }; }
  var emVoo = {}, controladores = {};
  function ler(r, tipo) { if (!r.ok) throw new Error("http " + r.status); return tipo === "json" ? r.json() : r.text(); }
  var CAB = { json: { Accept: "application/json" }, text: { "X-Fragmento": "1" } };
  window.exq = {
    debounce: debounce,
    pegar: function (url, tipo) {
      if (emVoo[url]) return emVoo[url];
      var p = fetch(url, { credentials: "same-origin", headers: CAB[tipo || "json"] }).then(function (r) { return ler(r, tipo || "json"); });
      emVoo[url] = p; var limpar = function () { delete emVoo[url]; }; p.then(limpar, limpar);
      return p;
    },
    ultima: function (chave, url, tipo) {
      if (controladores[chave]) controladores[chave].abort();
      var c = controladores[chave] = new AbortController();
      return fetch(url, { credentials: "same-origin", headers: CAB[tipo || "json"], signal: c.signal }).then(function (r) { return ler(r, tipo || "json"); });
    }
  };

  /* busca ao vivo: <form data-busca-viva> + <div data-resultado>. O servidor devolve só o miolo (X-Fragmento). Sem JS, o GET normal funciona. */
  function esqueletosLista(alvo, n) {
    alvo.textContent = "";
    for (var i = 0; i < n; i++) { var d = document.createElement("div"); d.className = "esqueleto esqueleto-linha"; alvo.appendChild(d); }
  }
  function iniciarBuscaViva() {
    if (!window.fetch || !window.AbortController) return;
    $$("form[data-busca-viva]").forEach(function (form) {
      var alvo = $("[data-resultado]"); if (!alvo) return;
      var espera = null;
      function endereco() {
        var u = new URL(form.getAttribute("action") || location.pathname, location.href);
        new FormData(form).forEach(function (v, k) { if (String(v).trim() !== "") u.searchParams.append(k, v); });
        return u;
      }
      function rodar() {
        var u = endereco();
        alvo.classList.add("carregando-lista"); alvo.setAttribute("aria-busy", "true");
        clearTimeout(espera); espera = setTimeout(function () { esqueletosLista(alvo, 5); }, 250);  // só aparece se a resposta demorar
        window.exq.ultima("busca:" + location.pathname, u.pathname + u.search, "text").then(function (html) {
          clearTimeout(espera); alvo.innerHTML = html;  // HTML do próprio servidor, já escapado pelo Jinja
          alvo.classList.remove("carregando-lista"); alvo.removeAttribute("aria-busy");
          aplicarVars(alvo); if (window.exqKatex) window.exqKatex(alvo);
          history.replaceState(null, "", u.pathname + u.search);
        }).catch(function (err) {
          if (err && err.name === "AbortError") return;  // substituída por uma busca mais nova
          clearTimeout(espera); form.submit();  // falha de rede: cai no envio comum do formulário
        });
      }
      var adiada = debounce(rodar, 300);
      form.addEventListener("input", function (e) {
        if (e.target.matches("input[type=search], input[type=text]")) { var n = e.target.value.trim().length; if (n === 1) return; adiada(); }
      });
      form.addEventListener("change", function (e) { if (e.target.matches("select, input[type=checkbox]")) rodar(); });
      form.addEventListener("submit", function (e) { e.preventDefault(); e.stopPropagation(); rodar(); });
    });
  }

  /* autocomplete: <input data-sugestoes="/url" list="id-do-datalist">. Mín. 2 letras, 250 ms de espera, cada termo é consultado uma só vez. */
  function iniciarSugestoes() {
    if (!window.fetch || !window.AbortController) return;
    $$("input[data-sugestoes]").forEach(function (inp) {
      var lista = document.getElementById(inp.getAttribute("list")), memoria = {};
      if (!lista) return;
      function preencher(itens) { lista.textContent = ""; itens.forEach(function (t) { var o = document.createElement("option"); o.value = t; lista.appendChild(o); }); }
      inp.addEventListener("input", debounce(function () {
        var q = inp.value.trim().toLowerCase(); if (q.length < 2) { preencher([]); return; }
        if (memoria[q]) { preencher(memoria[q]); return; }
        window.exq.ultima("sug:" + inp.id, inp.dataset.sugestoes + "?q=" + encodeURIComponent(q), "json")
          .then(function (d) { memoria[q] = d.itens; preencher(d.itens); }).catch(function () { /* sem sugestões; o campo continua livre */ });
      }, 250));
    });
  }

  function iniciar() {
    iniciarBuscaViva(); iniciarSugestoes();
    aplicarVars(document);
    var t = null; try { t = localStorage.getItem("exq-tema"); } catch (e) { /* ignore */ }
    $$("[data-tema]").forEach(function (b) { b.setAttribute("aria-pressed", String(b.getAttribute("data-tema") === (t || "auto"))); });
    animarReguas(); iniciarAvisos();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar); else iniciar();
})();
