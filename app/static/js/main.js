/* ═══════════════════════════════════════════════════
   ExQuest — main.js v4
   Fix definitivo sidebar mobile
═══════════════════════════════════════════════════ */

const CSRF = () => document.querySelector('meta[name="csrf-token"]')?.content || '';

// ── Custom confirm modal (replaces browser confirm()) ──
function exqConfirm(msg, onOk, opts={}) {
  let modal = document.getElementById('_exq-confirm-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = '_exq-confirm-modal';
    modal.innerHTML = `
      <div style="position:fixed;inset:0;background:rgba(0,0,0,.72);z-index:99999;display:flex;align-items:center;justify-content:center">
        <div style="background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius-xl);padding:28px 32px;max-width:380px;width:90%;text-align:center;box-shadow:0 16px 48px rgba(0,0,0,.6)">
          <div id="_exq-confirm-icon" style="font-size:28px;margin-bottom:10px">\u{26A0}\u{FE0F}</div>
          <div id="_exq-confirm-msg" style="font-size:15px;font-weight:600;margin-bottom:6px"></div>
          <div id="_exq-confirm-sub" style="font-size:13px;color:var(--text-muted);margin-bottom:22px"></div>
          <div style="display:flex;gap:12px;justify-content:center">
            <button id="_exq-confirm-cancel" class="btn btn-secondary">Cancelar</button>
            <button id="_exq-confirm-ok" class="btn btn-danger">Confirmar</button>
          </div>
        </div>
      </div>`;
    document.body.appendChild(modal);
  }
  document.getElementById('_exq-confirm-icon').textContent = opts.icon || '\u{26A0}\u{FE0F}';
  document.getElementById('_exq-confirm-msg').textContent = opts.title || 'Confirmar ação';
  document.getElementById('_exq-confirm-sub').textContent = msg;
  const okBtn = document.getElementById('_exq-confirm-ok');
  const cancelBtn = document.getElementById('_exq-confirm-cancel');
  okBtn.textContent = opts.okLabel || 'Confirmar';
  okBtn.className = 'btn ' + (opts.okClass || 'btn-danger');
  modal.style.display = 'flex';
  const close = () => { modal.style.display = 'none'; };
  okBtn.onclick = () => { close(); onOk(); };
  cancelBtn.onclick = close;
}

document.addEventListener('DOMContentLoaded', () => {

  // ── Flash auto-dismiss ────────────────────────────
  document.querySelectorAll('.alert').forEach(el => {
    el.querySelector('.alert-close')?.addEventListener('click', () => dismiss(el));
    setTimeout(() => dismiss(el), 3000);
  });

  function dismiss(el) {
    if (!el?.parentNode) return;
    el.style.transition = 'opacity .3s,transform .3s';
    el.style.opacity = '0'; el.style.transform = 'translateX(20px)';
    setTimeout(() => el.remove(), 320);
  }

  // ── Sidebar mobile ────────────────────────────────
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  const menuBtn = document.getElementById('menu-toggle');

  function openSidebar() {
    sidebar?.classList.add('open');
    overlay?.classList.add('show');
    menuBtn?.classList.add('active');
    // NÃO bloquear overflow do body — causa problemas em Safari/Chrome mobile
  }

  function closeSidebar() {
    sidebar?.classList.remove('open');
    overlay?.classList.remove('show');
    menuBtn?.classList.remove('active');
  }

  // Botão hamburger
  menuBtn?.addEventListener('click', e => {
    e.stopPropagation();
    sidebar?.classList.contains('open') ? closeSidebar() : openSidebar();
  });

  // Overlay fecha ao clicar fora
  overlay?.addEventListener('click', closeSidebar);

  // ── FIX PRINCIPAL: links da sidebar ──────────────
  // Em mobile, não usamos setTimeout nem preventDefault.
  // Deixamos o browser navegar normalmente; apenas removemos a classe 'open'
  // para que a sidebar feche visualmente enquanto a página carrega.
  sidebar?.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', function(e) {
      // Só age em viewport mobile
      if (window.innerWidth > 900) return;

      const href = this.getAttribute('href');

      // Links sem destino ou âncoras locais: só fecha
      if (!href || href === '#') {
        closeSidebar();
        return;
      }

      // Para links normais: fecha o menu imediatamente (sem setTimeout)
      // e deixa o navegador seguir o href naturalmente
      closeSidebar();
      // Não chama e.preventDefault() — navegação acontece normalmente
    });
  });

  // Fecha ao redimensionar para desktop
  window.addEventListener('resize', () => {
    if (window.innerWidth > 900) closeSidebar();
  });

  // ── Active nav link ───────────────────────────────
  const path = window.location.pathname;
  // Add data-path to each link in base.html via JS for reliable matching
  sidebar?.querySelectorAll('a.nav-link').forEach(link => {
    const href = link.getAttribute('href') || '';
    if (!href || href === '#') return;
    // Strip trailing slash for comparison
    const hNorm = href.replace(/\/$/, '') || '/';
    const pNorm = path.replace(/\/$/, '') || '/';
    
    let isActive = false;
    
    if (hNorm === pNorm) {
      isActive = true;
    } else if (hNorm === '/social') {
      // Social matches /social AND /social/grupo/... AND /social/buscar etc
      isActive = pNorm === '/social' || pNorm.startsWith('/social/');
    } else if (hNorm === '/' || hNorm === '/dashboard') {
      isActive = pNorm === '/' || pNorm === '/dashboard';
    } else if (hNorm === '/admin') {
      isActive = pNorm === '/admin';
    } else if (hNorm.length > 1 && pNorm.startsWith(hNorm + '/')) {
      isActive = true;
    }
    
    if (isActive) link.classList.add('active');
  });

  // ── Logout confirm ────────────────────────────────
  const logoutLink = document.getElementById('logout-nav-link');
  if (logoutLink) {
    logoutLink.addEventListener('click', function(e) {
      e.preventDefault();
      const url = this.dataset.logoutUrl;
      exqConfirm('Deseja mesmo sair da sua conta?', function() {
        window.location.href = url;
      }, {icon: '\u{1F6AA}', title: 'Sair da Conta', okLabel: 'Sair', okClass: 'btn-danger'});
    });
  }


  document.querySelectorAll('.progress-bar-fill[data-width]').forEach(bar => {
    requestAnimationFrame(() => setTimeout(() => bar.style.width = bar.dataset.width + '%', 80));
  });

  // ── Stagger animate-in ────────────────────────────
  document.querySelectorAll('.animate-in').forEach((el, i) => {
    el.style.animationDelay = (i * 0.055) + 's';
  });

  // ── Confirm delete ────────────────────────────────
  document.querySelectorAll('[data-confirm]').forEach(btn => {
    btn.addEventListener('click', e => {
      e.preventDefault();
      const msg = btn.dataset.confirm || 'Tem certeza?';
      const href = btn.getAttribute('href') || btn.dataset.href;
      exqConfirm(msg, function() {
        if (href) window.location = href;
        else btn.closest('form')?.submit();
      });
    });
  });

  // ── Questão discursiva: toggle campos admin ───────
  const tipoSelect = document.getElementById('tipo_questao');
  if (tipoSelect) {
    function toggleCampos() {
      const mult = document.getElementById('campos-multipla');
      const disc = document.getElementById('campos-discursiva');
      if (tipoSelect.value === 'multipla') {
        if (mult) mult.style.display = 'block';
        if (disc) disc.style.display = 'none';
      } else {
        if (mult) mult.style.display = 'none';
        if (disc) disc.style.display = 'block';
      }
    }
    tipoSelect.addEventListener('change', toggleCampos);
    toggleCampos();
  }

});

// ── Toggle senha ──────────────────────────────────
function toggleSenha(inputId, btn) {
  const input = document.getElementById(inputId);
  if (!input) return;
  const show = input.type === 'password';
  input.type = show ? 'text' : 'password';
  btn.querySelector('.eye-show').style.display = show ? 'none' : '';
  btn.querySelector('.eye-hide').style.display = show ? '' : 'none';
}

// ── API helper ─────────────────────────────────────
function apiPost(url, body) {
  return fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF() },
    body: JSON.stringify(body),
  });
}

// ── Toast global ──────────────────────────────────
function showToast(msg, tipo = 'info') {
  let c = document.getElementById('flash-container');
  if (!c) {
    c = document.createElement('div');
    c.id = 'flash-container';
    c.className = 'flash-container';
    document.body.appendChild(c);
  }
  const el = document.createElement('div');
  el.className = `alert alert-${tipo}`;
  el.innerHTML = `<span>${msg}</span><button class="alert-close" onclick="this.parentElement.remove()">✕</button>`;
  c.appendChild(el);
  setTimeout(() => el.remove(), 5000);
}

// ── Loja ──────────────────────────────────────────
function comprarItem(id, nome) {
  exqConfirm(`Deseja comprar "${nome}"?`, function() {
    apiPost(`/loja/comprar/${id}`, {}).then(r => r.json()).then(d => {
      if (d.ok) { showToast(`\u{2705} ${d.item} comprado! Moedas: ${d.moedas} \u{1FA99}`, 'success'); setTimeout(() => location.reload(), 1500); }
      else showToast('\u{274C} ' + d.erro, 'danger');
    });
  }, {icon:'\u{1F6D2}', title:'Confirmar Compra', okLabel:'Comprar', okClass:'btn-primary'});
}

function usarItem(id) {
  apiPost(`/loja/usar/${id}`, {}).then(r => r.json()).then(d => {
    showToast(d.ok ? '\u{2705} ' + d.msg : '\u{274C} ' + d.erro, d.ok ? 'success' : 'danger');
    if (d.ok) setTimeout(() => location.reload(), 1200);
  });
}

// ── Upload avatar/banner ──────────────────────────
function triggerIconUpload()   { document.getElementById('icon-file-input')?.click(); }
function triggerBannerUpload() { document.getElementById('banner-file-input')?.click(); }

function removerIcon() {
  exqConfirm('Remover sua foto de perfil?', function() {
    apiPost('/perfil/remover-icon', {}).then(() => location.reload());
  }, {icon:'\u{1F5BC}\u{FE0F}', title:'Remover Foto', okLabel:'Remover', okClass:'btn-danger'});
}
function removerBanner() {
  exqConfirm('Remover seu banner de perfil?', function() {
    apiPost('/perfil/remover-banner', {}).then(() => location.reload());
  }, {icon:'\u{1F5BC}\u{FE0F}', title:'Remover Banner', okLabel:'Remover', okClass:'btn-danger'});
}

// ── Amigos ────────────────────────────────────────
function adicionarAmigo(uid) {
  apiPost('/social/adicionar/' + uid, {}).then(r => r.json()).then(d => {
    d.ok ? showToast('\u{2705} ' + d.msg, 'success') : showToast('\u{274C} ' + d.erro, 'danger');
    if (d.ok) setTimeout(() => location.reload(), 1000);
  });
}
function aceitarAmigo(id) { apiPost('/social/aceitar/' + id, {}).then(() => location.reload()); }
function recusarAmigo(id) { apiPost('/social/recusar/' + id, {}).then(() => location.reload()); }
function removerAmigo(uid) {
  exqConfirm('Remover este amigo da sua lista?', function() {
    apiPost('/social/remover/' + uid, {}).then(() => location.reload());
  }, {icon:'\u{1F464}', title:'Remover Amigo', okLabel:'Remover', okClass:'btn-danger'});
}