/* ExQuest — gradient_builder.js
   Seletor visual de gradiente para nick Premium */

(function() {
  'use strict';

  let cores = ['#6366f1', '#f472b6'];
  let direcao = '135deg';

  function gerarGradiente() {
    return `linear-gradient(${direcao}, ${cores.join(', ')})`;
  }

  function atualizarPreview() {
    const preview = document.getElementById('gradient-preview-bar');
    const input   = document.getElementById('nick_gradiente');
    const grad    = gerarGradiente();
    if (preview) {
      preview.style.background = '';
      const nomeUser = preview.dataset.nome || 'Seu Nome';
      preview.innerHTML = `<span id="gradient-preview-text" style="background-image:${grad};background-clip:text;-webkit-background-clip:text;-webkit-text-fill-color:transparent;font-weight:800;font-size:18px">${nomeUser}</span>`;
    }
    if (input) input.value = grad;
  }

  function renderCores() {
    const container = document.getElementById('gradient-cores-container');
    if (!container) return;
    container.innerHTML = '';
    cores.forEach((cor, i) => {
      const div = document.createElement('div');
      div.className = 'gradient-color-stop';
      div.innerHTML = `
        <input type="color" value="${cor}" data-idx="${i}"
          style="width:40px;height:40px;border:none;background:none;cursor:pointer;border-radius:8px;padding:0;flex-shrink:0">
        <span style="font-size:13px;color:var(--text-muted)">${i===0?'Cor inicial':'Cor ' + (i+1)}</span>
        ${cores.length > 2 ? `<button type="button" onclick="window._gradientRemover(${i})" style="background:none;border:none;color:var(--rose);cursor:pointer;font-size:16px;padding:4px">✕</button>` : ''}`;
      div.querySelector('input[type="color"]').addEventListener('input', e => {
        cores[i] = e.target.value;
        atualizarPreview();
      });
      container.appendChild(div);
    });
  }

  window._gradientRemover = function(idx) {
    if (cores.length <= 2) return;
    cores.splice(idx, 1);
    renderCores();
    atualizarPreview();
  };

  document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('gradient-cores-container');
    if (!container) return;

    // Inicializar com valor existente
    const inputExistente = document.getElementById('nick_gradiente');
    if (inputExistente && inputExistente.value) {
      const match = inputExistente.value.match(/linear-gradient\(([^,]+),\s*(.+)\)$/);
      if (match) {
        direcao = match[1].trim();
        cores   = match[2].split(',').map(c => c.trim()).filter(c => c.startsWith('#'));
        if (cores.length < 2) cores = ['#6366f1', '#f472b6'];
      }
    }

    renderCores();
    atualizarPreview();

    // Botão adicionar cor
    document.getElementById('btn-add-cor')?.addEventListener('click', () => {
      if (cores.length >= 5) return;
      cores.push('#34d399');
      renderCores();
      atualizarPreview();
    });

    // Direção
    document.querySelectorAll('.gradient-dir-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.gradient-dir-btn').forEach(b => b.classList.remove('ativo'));
        btn.classList.add('ativo');
        direcao = btn.dataset.dir;
        atualizarPreview();
      });
      if (btn.dataset.dir === direcao) btn.classList.add('ativo');
    });
  });

})();
