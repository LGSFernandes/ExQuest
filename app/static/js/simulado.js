/* Cronômetro e contagem do simulado. O servidor é quem decide se o envio está dentro do tempo. */
(function () {
  "use strict";
  var f = document.getElementById("simulado");
  if (!f) return;
  var fim = Date.now() + parseInt(f.dataset.restante, 10) * 1000;
  var el = document.getElementById("cronometro"), cont = document.getElementById("contadas");
  function contar() {
    var feitas = {};
    Array.prototype.forEach.call(f.querySelectorAll("[data-marca]"), function (i) {
      if ((i.type === "radio" && i.checked) || (i.tagName === "TEXTAREA" && i.value.trim())) feitas[i.name] = 1;
    });
    cont.textContent = Object.keys(feitas).length;
  }
  f.addEventListener("input", contar); f.addEventListener("change", contar);
  var enviou = false;
  function tick() {
    var s = Math.max(0, Math.round((fim - Date.now()) / 1000));
    el.textContent = String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
    el.classList.toggle("acabando", s <= 60);
    if (s === 0 && !enviou) { enviou = true; f.dataset.confirmado = "1"; f.requestSubmit(); }
  }
  tick(); setInterval(tick, 1000);
})();
