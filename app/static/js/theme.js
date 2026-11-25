/* Aplica o tema salvo antes da primeira pintura (evita piscar). Carregado no <head>, sem defer. */
(function () {
  try {
    var t = localStorage.getItem("exq-tema");
    if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t);
  } catch (e) { /* armazenamento bloqueado: segue o tema do sistema */ }
})();
