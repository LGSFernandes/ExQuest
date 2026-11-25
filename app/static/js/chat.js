/* Chat por polling. Todo texto entra com textContent (nunca innerHTML).
   - Envio otimista: a mensagem aparece na hora (esmaecida) e é confirmada ou desfeita quando o servidor responde.
   - Sem chamadas duplicadas: no máximo 1 busca de novas em andamento; "anteriores" é paginado por cursor (id).
   - A lista mantém no máximo MAX_DOM mensagens; as antigas voltam pelo botão "Mensagens anteriores". */
(function () {
  var raiz = document.querySelector("[data-chat]");
  if (!raiz) return;
  var MAX_DOM = 300;
  var lista = raiz.querySelector("[data-lista]"), form = raiz.querySelector("[data-form]"), erro = raiz.querySelector("[data-erro]");
  var anexo = raiz.querySelector("[data-anexo]"), arq = form.querySelector("input[type=file]"), texto = form.querySelector("textarea");
  var maisBtn = raiz.querySelector("[data-mais]");
  var token = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
  var ultimo = 0, buscando = false, carregandoAntigas = false;
  function ids() { return lista.querySelectorAll("li[data-id]"); }
  function atualizarUltimo() { var l = ids(); ultimo = l.length ? parseInt(l[l.length - 1].dataset.id, 10) : 0; }  // só na carga inicial
  function mostrarErro(t) { erro.textContent = t || ""; erro.hidden = !t; }
  function noFim() { return lista.scrollHeight - lista.scrollTop - lista.clientHeight < 80; }

  function montar(m) {
    var li = document.createElement("li"); li.className = "chat-msg" + (m.meu ? " minha" : ""); if (m.id) li.dataset.id = m.id;
    var a = document.createElement("span"); a.className = "chat-autor"; a.textContent = m.autor + " ";
    var h = document.createElement("span"); h.className = "pauta-meta"; h.textContent = m.hora; a.appendChild(h); li.appendChild(a);
    if (m.texto) { var p = document.createElement("p"); p.className = "chat-texto"; p.textContent = m.texto; li.appendChild(p); }
    if (m.imagem) { var im = document.createElement("img"); im.className = "chat-img"; im.src = m.imagem; im.alt = "Imagem enviada por " + m.autor; im.loading = "lazy"; im.decoding = "async"; li.appendChild(im); }
    return li;
  }
  function adicionar(m) {
    if (lista.querySelector('li[data-id="' + m.id + '"]')) return;
    var li = montar(m);
    var depoisDe = null, itens = ids();  // mantém a ordem por id (resposta própria pode chegar antes de msgs antigas de outros)
    for (var i = 0; i < itens.length; i++) { if (parseInt(itens[i].dataset.id, 10) > m.id) { depoisDe = itens[i]; break; } }
    lista.insertBefore(li, depoisDe); if (window.exqKatex && m.texto) window.exqKatex(li);
  }
  function podar() {
    var l = ids(), sobra = l.length - MAX_DOM;
    for (var i = 0; i < sobra; i++) l[i].remove();
    if (sobra > 0 && maisBtn) maisBtn.hidden = false;
  }
  function receber(msgs, daBusca) {
    var fim = noFim(); msgs.forEach(adicionar);
    if (daBusca) msgs.forEach(function (m) { if (m.id > ultimo) ultimo = m.id; });  // a própria mensagem enviada NÃO avança o cursor: o polling ainda busca o que veio antes dela
    if (fim) { podar(); lista.scrollTop = lista.scrollHeight; }
  }

  function buscar() {
    if (document.hidden || buscando) return;
    buscando = true;
    fetch(raiz.dataset.novas + "?depois=" + ultimo, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
      .then(function (d) { if (d.mensagens.length) receber(d.mensagens, true); })
      .catch(function () { /* falha momentânea: tenta de novo no próximo ciclo */ })
      .then(function () { buscando = false; });
  }

  /* histórico paginado: esqueletos enquanto carrega e a posição de leitura não pula */
  function esqueletos(n) {
    var fr = document.createDocumentFragment();
    for (var i = 0; i < n; i++) { var li = document.createElement("li"); li.className = "chat-msg esqueleto esqueleto-msg"; li.setAttribute("aria-hidden", "true"); li.dataset.esqueleto = "1"; fr.appendChild(li); }
    lista.insertBefore(fr, lista.firstChild);
  }
  if (maisBtn) maisBtn.addEventListener("click", function () {
    if (carregandoAntigas) return;
    var primeiro = ids()[0]; if (!primeiro) return;
    carregandoAntigas = true; maisBtn.setAttribute("aria-busy", "true"); esqueletos(3);
    fetch(raiz.dataset.anteriores + "?antes=" + primeiro.dataset.id, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
      .then(function (d) {
        Array.prototype.forEach.call(lista.querySelectorAll("[data-esqueleto]"), function (e) { e.remove(); });
        var altura = lista.scrollHeight, topo = lista.scrollTop, ref = ids()[0], fr = document.createDocumentFragment();
        d.mensagens.forEach(function (m) { var li = montar(m); fr.appendChild(li); });
        lista.insertBefore(fr, ref);
        if (window.exqKatex) window.exqKatex(lista);
        lista.scrollTop = topo + (lista.scrollHeight - altura);  // mantém o que o aluno estava lendo
        maisBtn.hidden = !d.tem_mais;
      })
      .catch(function () { Array.prototype.forEach.call(lista.querySelectorAll("[data-esqueleto]"), function (e) { e.remove(); }); mostrarErro("Não foi possível carregar as mensagens anteriores."); })
      .then(function () { carregandoAntigas = false; maisBtn.removeAttribute("aria-busy"); });
  });

  arq.addEventListener("change", function () { anexo.hidden = !arq.files.length; anexo.textContent = arq.files.length ? "Imagem anexada: " + arq.files[0].name : ""; });

  /* envio otimista */
  var seq = 0;
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var conteudo = texto.value, tinhaImagem = arq.files.length > 0;
    if (!conteudo.trim() && !tinhaImagem) return;
    mostrarErro("");
    var corpo = new FormData(form);
    var prov = montar({ meu: true, autor: "Você", hora: "enviando…", texto: conteudo.trim() || (tinhaImagem ? "Enviando imagem…" : "") });
    prov.classList.add("pendente"); prov.dataset.pendente = String(++seq); prov.setAttribute("aria-busy", "true");
    lista.appendChild(prov); lista.scrollTop = lista.scrollHeight;
    texto.value = ""; arq.value = ""; anexo.hidden = true;
    fetch(raiz.dataset.enviar, { method: "POST", credentials: "same-origin", headers: { "X-CSRFToken": token }, body: corpo })
      .then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.erro || "Não foi possível enviar."); return d; }); })
      .then(function (d) { prov.remove(); receber([d.mensagem], false); lista.scrollTop = lista.scrollHeight; buscar(); })
      .catch(function (err) {
        prov.remove();  // desfaz: a mensagem não foi enviada
        if (!texto.value) texto.value = conteudo;  // devolve o texto para o aluno não perder o que escreveu
        mostrarErro(err.message + (tinhaImagem ? " Anexe a imagem novamente." : ""));
      });
  });
  texto.addEventListener("keydown", function (e) { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) form.requestSubmit(); });
  atualizarUltimo(); lista.scrollTop = lista.scrollHeight;
  setInterval(buscar, 4000);
  document.addEventListener("visibilitychange", function () { if (!document.hidden) buscar(); });
})();
