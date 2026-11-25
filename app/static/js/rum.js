/* Medição de velocidade com usuários reais (Core Web Vitals). Anônimo: manda só rota, aparelho (celular/computador),
   tipo de conexão e os tempos. Uma única mensagem por visita, ao sair da página. */
(function () {
  if (!window.PerformanceObserver || !navigator.sendBeacon) return;
  var tag = document.currentScript, d = tag ? tag.dataset : {};
  if (!d.rota || Math.random() > parseFloat(d.amostra || "1")) return;
  var m = {}, cls = 0, janela = 0, janelaIni = 0, ultimoLs = 0, inp = 0;
  function obs(tipo, fn, extra) {
    try { var o = new PerformanceObserver(function (l) { l.getEntries().forEach(fn); }); o.observe(Object.assign({ type: tipo, buffered: true }, extra || {})); } catch (e) { /* tipo não suportado */ }
  }
  obs("paint", function (e) { if (e.name === "first-contentful-paint") m.FCP = e.startTime; });
  obs("largest-contentful-paint", function (e) { m.LCP = e.startTime; });
  obs("layout-shift", function (e) {
    if (e.hadRecentInput) return;
    // CLS = pior "janela de sessão" (intervalo < 1 s entre mudanças, máx. 5 s), como definido em web.dev
    if (e.startTime - ultimoLs > 1000 || e.startTime - janelaIni > 5000) { janela = 0; janelaIni = e.startTime; }
    janela += e.value; ultimoLs = e.startTime; if (janela > cls) { cls = janela; m.CLS = Math.round(cls * 1000) / 1000; }
  });
  obs("event", function (e) { if (e.interactionId && e.duration > inp) { inp = e.duration; m.INP = inp; } }, { durationThreshold: 40 });
  var nav = performance.getEntriesByType("navigation")[0];
  if (nav) m.TTFB = nav.responseStart;
  var enviado = false;
  function enviar() {
    if (enviado || !Object.keys(m).length) return;
    enviado = true;
    var c = navigator.connection && navigator.connection.effectiveType;
    var corpo = { rota: d.rota, d: (matchMedia("(pointer: coarse)").matches || innerWidth < 768) ? "movel" : "desktop", c: c || "", m: m };
    navigator.sendBeacon("/rum", new Blob([JSON.stringify(corpo)], { type: "application/json" }));
  }
  document.addEventListener("visibilitychange", function () { if (document.visibilityState === "hidden") enviar(); });
  addEventListener("pagehide", enviar);
})();
