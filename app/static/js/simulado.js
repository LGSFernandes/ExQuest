/* ═══════════════════════════════════════════════════
   ExQuest — simulado.js v3
   Múltipla escolha + Discursiva + Timer + IA feedback
═══════════════════════════════════════════════════ */
(function () {
  'use strict';
  const CSRF = () => document.querySelector('meta[name="csrf-token"]')?.content || '';
  let totalQuestoes = 0, respondidas = 0, acertos = 0;
  let tempoRestante = 0, timerInterval = null;
  const estados = {};

  document.addEventListener('DOMContentLoaded', init);

  function init() {
    const cards = document.querySelectorAll('.questao-card');
    totalQuestoes = cards.length;
    const container = document.getElementById('simulado-container');
    const tempoMin  = parseInt(container?.dataset.tempoMin || 0);
    tempoRestante   = tempoMin * 60;

    cards.forEach(card => {
      const qid  = card.dataset.questaoId;
      const tipo = card.dataset.tipo || 'multipla';
      estados[qid] = { selecionada: null, respondida: false, tipo };

      if (tipo === 'multipla') {
        card.querySelectorAll('.alternativa-btn').forEach(btn =>
          btn.addEventListener('click', () => handleSelecionar(card, btn)));
      }
      card.querySelector('.btn-confirmar')
          ?.addEventListener('click', () => handleConfirmar(card));
    });

    updateProgressBar();
    if (tempoRestante > 0) iniciarTimer();
  }

  // ── Timer ──────────────────────────────────────────
  function iniciarTimer() {
    const display = document.getElementById('timer-display');
    timerInterval = setInterval(() => {
      tempoRestante--;
      if (display) {
        const m = String(Math.floor(tempoRestante/60)).padStart(2,'0');
        const s = String(tempoRestante%60).padStart(2,'0');
        display.textContent = `${m}:${s}`;
        display.className   = 'timer-display' + (tempoRestante < 60 ? ' urgente' : '');
      }
      if (tempoRestante <= 0) { clearInterval(timerInterval); encerrarSimulado(true); }
    }, 1000);
  }

  function encerrarSimulado(timeUp=false) {
    clearInterval(timerInterval);
    document.querySelectorAll('.questao-card').forEach(card => {
      if (!estados[card.dataset.questaoId]?.respondida)
        handleConfirmar(card, true);
    });
    setTimeout(() => mostrarResultado(timeUp), 800);
  }

  // ── Selecionar alternativa ─────────────────────────
  function handleSelecionar(card, btn) {
    const qid = card.dataset.questaoId;
    if (estados[qid].respondida) return;
    card.querySelectorAll('.alternativa-btn').forEach(b => b.classList.remove('selected'));
    btn.classList.add('selected');
    estados[qid].selecionada = btn.dataset.alternativaId;
    const cb = card.querySelector('.btn-confirmar');
    if (cb) { cb.disabled = false; cb.className = 'btn btn-primary btn-confirmar'; cb.textContent = 'Confirmar Resposta'; }
  }

  // ── Confirmar ──────────────────────────────────────
  async function handleConfirmar(card, forcado=false) {
    const qid   = card.dataset.questaoId;
    const estado= estados[qid];
    if (estado.respondida) return;

    const tipo  = estado.tipo;
    const cb    = card.querySelector('.btn-confirmar');

    if (tipo === 'multipla') {
      if (!estado.selecionada && !forcado) return;
      if (forcado && !estado.selecionada) {
        const primeira = card.querySelector('.alternativa-btn');
        if (!primeira) { estado.respondida=true; respondidas++; updateProgressBar(); return; }
        estado.selecionada = primeira.dataset.alternativaId;
      }
      if (cb) { cb.disabled=true; cb.textContent='Verificando…'; }
      try {
        const res  = await fetch('/api/responder', {
          method:'POST', headers:{'Content-Type':'application/json','X-CSRFToken':CSRF()},
          body: JSON.stringify({ questao_id:parseInt(qid), alternativa_id:parseInt(estado.selecionada), modo:'simulado' })
        });
        const data = await res.json();
        if (data.limite) { showToast('Limite atingido!','warning'); return; }
        estado.respondida=true; respondidas++; if(data.acertou) acertos++;
        renderFeedbackMultipla(card, data, estado.selecionada);
        updateProgressBar(); updateXPWidget(data);
        proximaQuestao(card);
        if (respondidas===totalQuestoes) { clearInterval(timerInterval); setTimeout(()=>mostrarResultado(),700); }
      } catch { if(cb){cb.disabled=false;cb.textContent='Confirmar Resposta';} }

    } else {
      // Discursiva
      const textarea = card.querySelector('.resposta-discursiva');
      const texto    = textarea?.value?.trim() || '';
      if (!texto && !forcado) { showToast('Escreva sua resposta primeiro.','warning'); return; }
      if (cb) { cb.disabled=true; cb.textContent='Avaliando com IA…'; }
      try {
        const res  = await fetch('/api/responder-discursiva', {
          method:'POST', headers:{'Content-Type':'application/json','X-CSRFToken':CSRF()},
          body: JSON.stringify({ questao_id:parseInt(qid), resposta_texto:texto||'(sem resposta)', modo:'simulado' })
        });
        const data = await res.json();
        estado.respondida=true; respondidas++; if(data.acertou) acertos++;
        renderFeedbackDiscursiva(card, data);
        updateProgressBar(); updateXPWidget(data);
        proximaQuestao(card);
        if (respondidas===totalQuestoes) { clearInterval(timerInterval); setTimeout(()=>mostrarResultado(),700); }
      } catch { if(cb){cb.disabled=false;cb.textContent='Confirmar Resposta';} }
    }
  }

  function proximaQuestao(card) {
    const cards  = Array.from(document.querySelectorAll('.questao-card'));
    const proxima= cards.find(c => !estados[c.dataset.questaoId]?.respondida);
    if (proxima) setTimeout(()=>proxima.scrollIntoView({behavior:'smooth',block:'start'}),500);
  }

  // ── Feedback múltipla ──────────────────────────────
  function renderFeedbackMultipla(card, data, altId) {
    const cId = String(data.alternativa_correta_id);
    card.querySelectorAll('.alternativa-btn').forEach(btn => {
      btn.disabled = true;
      const bid = String(btn.dataset.alternativaId);
      const letra = btn.querySelector('.alternativa-letra');
      if (bid===cId) { btn.classList.remove('selected'); btn.classList.add('correta'); if(letra) letra.textContent='✓'; }
      else if (bid===String(altId) && !data.acertou) { btn.classList.remove('selected'); btn.classList.add('errada'); if(letra) letra.textContent='✗'; }
    });
    renderResultBox(card, data.acertou, data.xp_ganho, data.moedas_ganhas, data.explicacao);
    const cb = card.querySelector('.btn-confirmar');
    if(cb){ cb.textContent=data.acertou?'✓ Acertou!':'✗ Errou'; cb.className=`btn btn-confirmar ${data.acertou?'btn-secondary':'btn-danger'}`; }
  }

  // ── Feedback discursiva ────────────────────────────
  function renderFeedbackDiscursiva(card, data) {
    const box = card.querySelector('.resultado-box');
    if (!box) return;
    const cor   = data.acertou ? 'acerto' : 'erro';
    const emoji = data.acertou ? '\u{1F389}' : '\u{1F4DD}';
    const nota  = data.nota_ia || 0;
    const barColor = nota >= 70 ? 'var(--emerald)' : nota >= 40 ? 'var(--gold)' : 'var(--rose)';
    box.className = `resultado-box ${cor}`;
    box.style.display = 'block';
    box.innerHTML = `
      <strong>${emoji} ${data.acertou ? 'Resposta Correta!' : 'Resposta Incorreta'}</strong>
      <div style="margin-top:10px">
        <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px">
          <span>Pontuação IA</span><span style="font-weight:700">${nota}%</span>
        </div>
        <div style="background:rgba(255,255,255,.06);border-radius:99px;height:6px;overflow:hidden">
          <div class="nota-ia-bar" style="width:${nota}%;background:${barColor}"></div>
        </div>
      </div>
      ${data.feedback ? `<p style="margin-top:10px;font-size:13px;opacity:.9;line-height:1.5">\u{1F4AC} ${data.feedback}</p>` : ''}
      ${data.acertou ? `<div class="resultado-recompensa mt-8"><span class="recompensa-chip">\u{26A1} +${data.xp_ganho} XP</span><span class="recompensa-chip">\u{1FA99} +${data.moedas_ganhas}</span></div>` : ''}
      ${data.explicacao ? `<p style="margin-top:8px;font-size:12px;color:var(--text-dim)">${data.explicacao}</p>` : ''}
    `;
    // Animar barra após render
    requestAnimationFrame(() => {
      setTimeout(() => { const b = box.querySelector('.nota-ia-bar'); if(b) b.style.width=nota+'%'; }, 50);
    });
    const cb = card.querySelector('.btn-confirmar');
    if(cb){ cb.textContent=data.acertou?'✓ Correto!':'Avaliado'; cb.className=`btn btn-confirmar ${data.acertou?'btn-secondary':'btn-danger'}`; }
  }

  function renderResultBox(card, acertou, xp, moedas, explicacao) {
    const box = card.querySelector('.resultado-box');
    if (!box) return;
    box.className = `resultado-box ${acertou?'acerto':'erro'}`;
    box.style.display = 'block';
    box.innerHTML = `<strong>${acertou?'\u{1F389} Correto!':'\u{1F614} Incorreto!'}</strong>
      ${acertou?`<div class="resultado-recompensa mt-8"><span class="recompensa-chip">\u{26A1} +${xp} XP</span><span class="recompensa-chip">\u{1FA99} +${moedas}</span></div>`:''}
      ${explicacao?`<p class="mt-8" style="font-size:13px;opacity:.85">${explicacao}</p>`:''}`;
  }

  // ── Progress bar ───────────────────────────────────
  function updateProgressBar() {
    const bar  = document.getElementById('simulado-progress-fill');
    const lbl  = document.getElementById('simulado-progress-label');
    const pct  = totalQuestoes ? Math.round(respondidas/totalQuestoes*100) : 0;
    if(bar) bar.style.width = pct+'%';
    if(lbl) lbl.textContent = `${respondidas}/${totalQuestoes} respondidas`;
  }

  // ── XP Widget ──────────────────────────────────────
  let xpTimeout;
  function updateXPWidget(data) {
    let w = document.getElementById('xp-bar-live');
    if (!w) { w=document.createElement('div'); w.id='xp-bar-live'; w.className='xp-bar-live'; document.body.appendChild(w); }
    w.innerHTML = `
      <div style="display:flex;justify-content:space-between;margin-bottom:8px">
        <span style="font-size:13px;font-weight:600;color:var(--text-muted)">Nível ${data.nivel}</span>
        <span style="font-size:12px;color:var(--primary-light)">\u{26A1} ${data.xp_total} XP</span>
      </div>
      <div class="progress-bar-wrap"><div class="progress-bar-fill" style="width:${data.progresso_nivel}%"></div></div>
      <div style="display:flex;justify-content:space-between;margin-top:8px;font-size:12px;color:var(--text-dim)">
        <span>\u{1F525} ${data.streak}</span><span>\u{1FA99} ${data.moedas_total}</span>
      </div>`;
    w.classList.add('show');
    clearTimeout(xpTimeout);
    xpTimeout = setTimeout(() => w.classList.remove('show'), 4500);
  }

  // ── Resultado final ────────────────────────────────
  function mostrarResultado(timeUp=false) {
    const pct      = totalQuestoes ? Math.round(acertos/totalQuestoes*100) : 0;
    const estrelas = pct >= 80 ? '\u{2B50}\u{2B50}\u{2B50}' : pct >= 60 ? '\u{2B50}\u{2B50}' : '\u{2B50}';
    const modal    = document.createElement('div');
    modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.75);display:flex;align-items:center;justify-content:center;z-index:9000;backdrop-filter:blur(8px)';
    modal.innerHTML = `
      <div style="background:rgba(13,16,23,.97);border:1px solid var(--border);border-radius:var(--radius-xl);padding:40px;max-width:440px;width:90%;text-align:center;animation:fadeInUp .4s ease">
        ${timeUp?'<p style="color:var(--rose);font-weight:600;margin-bottom:12px">\u{23F0} Tempo esgotado!</p>':''}
        <div style="font-size:48px;margin-bottom:14px">${estrelas}</div>
        <h2 style="font-family:var(--font-display);font-size:22px;margin-bottom:6px">Simulado concluído!</h2>
        <p style="color:var(--text-muted);margin-bottom:18px">Você acertou <strong style="color:var(--text)">${acertos} de ${totalQuestoes}</strong> questões</p>
        <div style="font-size:46px;font-family:var(--font-display);font-weight:800;background:linear-gradient(135deg,var(--primary),var(--accent));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;margin-bottom:24px">${pct}%</div>
        <div style="display:flex;gap:10px;justify-content:center">
          <a href="/simulado" class="btn btn-secondary">Novo Simulado</a>
          <a href="/dashboard" class="btn btn-primary">Dashboard</a>
        </div>
      </div>`;
    document.body.appendChild(modal);
    modal.addEventListener('click', e => { if(e.target===modal) modal.remove(); });
  }

  function showToast(msg, tipo) { if(window.showToast) window.showToast(msg,tipo); }
})();
