/* ExQuest — torneio.js
   Timer, submissão de respostas e anti-cheat de torneio */

(function() {
  'use strict';

  const CSRF = () => document.querySelector('meta[name="csrf-token"]')?.content || '';

  let torneioId      = null;
  let tempoRestante  = 0;
  let timerInterval  = null;
  let totalQuestoes  = 0;
  let respondidas    = 0;
  const temposResposta = [];   // para anti-cheat
  const acertosLista   = [];
  let tsUltimaResposta = Date.now();

  document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('torneio-container');
    if (!container) return;

    torneioId     = parseInt(container.dataset.torneioId);
    tempoRestante = parseInt(container.dataset.tempoMin || 0) * 60;
    totalQuestoes = document.querySelectorAll('.questao-card').length;

    document.querySelectorAll('.questao-card').forEach(card => {
      card.querySelectorAll('.alternativa-btn').forEach(btn => {
        btn.addEventListener('click', () => selecionarAlternativa(card, btn));
      });
      card.querySelector('.btn-confirmar')?.addEventListener('click',
        () => confirmarResposta(card));
    });

    if (tempoRestante > 0) iniciarTimer();
    atualizarProgressoTorneio();
  });

  function iniciarTimer() {
    const display = document.getElementById('torneio-timer');
    timerInterval = setInterval(() => {
      tempoRestante--;
      if (display) {
        const m = String(Math.floor(tempoRestante/60)).padStart(2,'0');
        const s = String(tempoRestante % 60).padStart(2,'0');
        display.textContent = `${m}:${s}`;
        display.className   = 'torneio-timer' + (tempoRestante < 60 ? ' urgente' : '');
      }
      if (tempoRestante <= 0) {
        clearInterval(timerInterval);
        encerrarTorneio(true);
      }
    }, 1000);
  }

  function selecionarAlternativa(card, btn) {
    const qid = card.dataset.questaoId;
    if (card.dataset.respondida === 'true') return;
    card.querySelectorAll('.alternativa-btn').forEach(b => b.classList.remove('selected'));
    btn.classList.add('selected');
    card.dataset.selecionada = btn.dataset.alternativaId;
    const cb = card.querySelector('.btn-confirmar');
    if (cb) { cb.disabled = false; cb.className = 'btn btn-primary btn-confirmar'; cb.textContent = 'Confirmar'; }
  }

  async function confirmarResposta(card, forcado = false) {
    if (card.dataset.respondida === 'true') return;
    const altId = card.dataset.selecionada;
    if (!altId && !forcado) return;

    // Anti-cheat: registrar tempo
    const agora     = Date.now();
    const tempoResp = (agora - tsUltimaResposta) / 1000;
    tsUltimaResposta = agora;
    temposResposta.push(tempoResp);

    const cb = card.querySelector('.btn-confirmar');
    if (cb) { cb.disabled = true; cb.textContent = 'Enviando…'; }

    try {
      const res = await fetch('/api/competicoes/responder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF() },
        body: JSON.stringify({
          torneio_id:     torneioId,
          questao_id:     parseInt(card.dataset.questaoId),
          alternativa_id: altId ? parseInt(altId) : null,
          tempo_segundos: tempoResp
        })
      });
      const data = await res.json();
      if (!res.ok) { showToast(data.erro || 'Erro.', 'danger'); if(cb){cb.disabled=false;cb.textContent='Confirmar';} return; }

      card.dataset.respondida = 'true';
      respondidas++;
      acertosLista.push(data.acertou);

      // Feedback visual
      const cId = String(data.alternativa_correta_id);
      card.querySelectorAll('.alternativa-btn').forEach(btn => {
        btn.disabled = true;
        const bid = String(btn.dataset.alternativaId);
        const letra = btn.querySelector('.alternativa-letra');
        if (bid === cId)   { btn.classList.add('correta'); if(letra) letra.textContent='✓'; }
        else if (bid === String(altId) && !data.acertou) { btn.classList.add('errada'); if(letra) letra.textContent='✗'; }
      });

      const box = card.querySelector('.resultado-box');
      if (box) {
        box.className = `resultado-box ${data.acertou ? 'acerto' : 'erro'}`;
        box.style.display = 'block';
        box.innerHTML = `<strong>${data.acertou ? '\u{2705} +'+data.pontos+' pts' : '\u{274C} Errou'}</strong>
          <div style="font-size:13px;margin-top:6px;opacity:.8">Pontuação total: <strong>${data.pontuacao_total}</strong> pts</div>
          ${data.explicacao ? `<p style="font-size:12px;margin-top:6px;opacity:.7">${data.explicacao}</p>` : ''}`;
      }

      if (cb) { cb.textContent = data.acertou ? '✓ Acertou!' : '✗ Errou'; cb.className = `btn btn-confirmar ${data.acertou?'btn-secondary':'btn-danger'}`; }

      // Atualizar pontuação
      const ptEl = document.getElementById('minha-pontuacao');
      if (ptEl) ptEl.textContent = data.pontuacao_total;

      atualizarProgressoTorneio();

      if (data.finalizado || respondidas >= totalQuestoes) {
        clearInterval(timerInterval);
        setTimeout(() => mostrarResultadoFinal(data.pontuacao_total), 600);
      } else {
        // Scroll para próxima
        const cards = Array.from(document.querySelectorAll('.questao-card'));
        const prox  = cards.find(c => c.dataset.respondida !== 'true');
        if (prox) setTimeout(() => prox.scrollIntoView({behavior:'smooth',block:'start'}), 400);
      }
    } catch(e) {
      if (cb) { cb.disabled=false; cb.textContent='Confirmar'; }
      showToast('Erro ao enviar.', 'danger');
    }
  }

  function encerrarTorneio(timeUp = false) {
    clearInterval(timerInterval);
    document.querySelectorAll('.questao-card').forEach(card => {
      if (card.dataset.respondida !== 'true') confirmarResposta(card, true);
    });
    setTimeout(() => mostrarResultadoFinal(null, timeUp), 800);
  }

  function atualizarProgressoTorneio() {
    const bar   = document.getElementById('torneio-progress-fill');
    const label = document.getElementById('torneio-progress-label');
    const pct   = totalQuestoes ? Math.round(respondidas/totalQuestoes*100) : 0;
    if (bar)   bar.style.width   = pct + '%';
    if (label) label.textContent = `${respondidas}/${totalQuestoes}`;
  }

  function mostrarResultadoFinal(pontos, timeUp = false) {
    const modal = document.createElement('div');
    modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.8);display:flex;align-items:center;justify-content:center;z-index:9000;backdrop-filter:blur(8px)';
    const acertos = acertosLista.filter(Boolean).length;
    modal.innerHTML = `
      <div style="background:rgba(13,16,23,.97);border:1px solid var(--border);border-radius:var(--radius-xl);padding:40px;max-width:440px;width:90%;text-align:center;animation:fadeInUp .4s ease">
        ${timeUp ? '<p style="color:var(--rose);font-weight:600;margin-bottom:12px">\u{23F0} Tempo esgotado!</p>' : ''}
        <div style="font-size:52px;margin-bottom:14px">\u{1F3C1}</div>
        <h2 style="font-family:var(--font-display);font-size:22px;margin-bottom:6px">Torneio concluído!</h2>
        <p style="color:var(--text-muted);margin-bottom:16px">
          Você acertou <strong style="color:var(--text)">${acertos}/${respondidas}</strong> questões
        </p>
        ${pontos !== null ? `<div style="font-size:48px;font-family:var(--font-display);font-weight:800;color:var(--gold);margin-bottom:20px">${pontos} pts</div>` : ''}
        <p style="font-size:13px;color:var(--text-muted);margin-bottom:24px">
          \u{1F3C6} As recompensas serão distribuídas ao final do torneio!
        </p>
        <div style="display:flex;gap:12px;justify-content:center">
          <a href="/competicoes" class="btn btn-secondary">← Competições</a>
          <a href="/dashboard"   class="btn btn-primary">Dashboard</a>
        </div>
      </div>`;
    document.body.appendChild(modal);
  }

  function showToast(msg, tipo) { if (window.showToast) window.showToast(msg, tipo); }

})();
