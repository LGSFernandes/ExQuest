/* ExQuest — ads.js
   Sistema de anúncios para usuários Free
   Totalmente controlado no servidor — sem SDK externo */

(function() {
  'use strict';

  const CSRF = () => document.querySelector('meta[name="csrf-token"]')?.content || '';

  // ── Abrir modal de vídeo publicitário ─────────────
  window.abrirVideoAd = function() {
    const modal = document.getElementById('ads-video-modal');
    if (!modal) return;
    modal.classList.add('show');

    const DURACAO = 15; // segundos
    let tempo = DURACAO;
    const countdownEl = document.getElementById('ads-countdown');
    const btnPular    = document.getElementById('btn-pular-ad');
    const btnColetar  = document.getElementById('btn-coletar-ad');

    if (btnPular)   btnPular.style.display   = 'none';
    if (btnColetar) btnColetar.style.display = 'none';
    if (countdownEl) countdownEl.textContent = tempo + 's';

    const interval = setInterval(() => {
      tempo--;
      if (countdownEl) countdownEl.textContent = tempo + 's';
      if (tempo <= 5 && btnPular) btnPular.style.display = 'inline-flex';
      if (tempo <= 0) {
        clearInterval(interval);
        if (countdownEl) countdownEl.textContent = '✓';
        if (btnPular)    btnPular.style.display   = 'none';
        if (btnColetar)  btnColetar.style.display = 'inline-flex';
      }
    }, 1000);

    modal._interval = interval;
  };

  window.fecharVideoAd = function() {
    const modal = document.getElementById('ads-video-modal');
    if (!modal) return;
    if (modal._interval) clearInterval(modal._interval);
    modal.classList.remove('show');
  };

  window.coletarRecompensaAd = function() {
    fetch('/api/ads/assistir', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF() },
      body: JSON.stringify({ tipo: 'video' })
    })
    .then(r => r.json())
    .then(d => {
      fecharVideoAd();
      if (d.ok) {
        showToast(`\u{1F389} +${d.questoes_extras} questões extras desbloqueadas! Restantes hoje: ${d.questoes_restantes}`, 'success');
        // Atualizar contador na página se existir
        const el = document.getElementById('questoes-restantes-count');
        if (el && d.questoes_restantes !== undefined) el.textContent = d.questoes_restantes;
      } else {
        showToast('\u{274C} ' + (d.erro || 'Erro ao coletar recompensa.'), 'danger');
      }
    })
    .catch(() => showToast('Erro de conexão.', 'danger'));
  };

  // ── Verificar status de ads ao carregar ───────────
  document.addEventListener('DOMContentLoaded', () => {
    const adsWidget = document.getElementById('ads-status-widget');
    if (!adsWidget) return;

    fetch('/api/ads/status')
      .then(r => r.json())
      .then(d => {
        if (!d.tem_ads) { adsWidget.style.display = 'none'; return; }
        const restCount = document.getElementById('questoes-restantes-count');
        if (restCount) restCount.textContent = d.questoes_restantes;
        // Mostrar/ocultar botão de assistir
        const btnWatch = document.getElementById('btn-watch-ad');
        if (btnWatch) btnWatch.disabled = !d.pode_assistir;
        const credEl = document.getElementById('ads-creditos-hoje');
        if (credEl) credEl.textContent = `${d.creditos_hoje}/${d.max_creditos_dia}`;
      });
  });

})();
