/* ════════════════════════════════════════════════════
   ExQuest — efeitos.js
   Canvas particles/matrix/stars — 100% gratuito,
   sem bibliotecas externas pagas.
   Ativado automaticamente quando body tem classe de efeito.
════════════════════════════════════════════════════ */

(function() {
  'use strict';

  // Detectar efeito ativo no body
  const body = document.body;

  function getEfeitoAtivo() {
    const efeitos = ['efeito-particles-gold','efeito-particles-purple','efeito-particles-blue',
                     'efeito-cosmos','efeito-matrix','efeito-fogo','efeito-chuva','efeito-bokeh'];
    return efeitos.find(e => body.classList.contains(e)) || null;
  }

  function criarCanvas() {
    const c = document.createElement('canvas');
    c.id = 'efeito-canvas';
    c.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:0;opacity:.55';
    document.body.insertBefore(c, document.body.firstChild);
    c.width  = window.innerWidth;
    c.height = window.innerHeight;
    window.addEventListener('resize', () => { c.width = window.innerWidth; c.height = window.innerHeight; });
    return c;
  }

  // ── Partículas (3 cores) ──────────────────────────
  function initParticulas(cor) {
    const canvas = criarCanvas();
    const ctx    = canvas.getContext('2d');
    let mouse    = { x: canvas.width/2, y: canvas.height/2 };
    const N = 60;
    const particles = Array.from({length: N}, () => ({
      x: Math.random()*canvas.width, y: Math.random()*canvas.height,
      vx: (Math.random()-.5)*.8, vy: (Math.random()-.5)*.8,
      r: Math.random()*2.5+1, alpha: Math.random()*.7+.3
    }));

    document.addEventListener('mousemove', e => { mouse.x = e.clientX; mouse.y = e.clientY; });

    function hexToRgb(hex) {
      const r = parseInt(hex.slice(1,3),16), g = parseInt(hex.slice(3,5),16), b = parseInt(hex.slice(5,7),16);
      return `${r},${g},${b}`;
    }
    const rgb = hexToRgb(cor);

    function draw() {
      ctx.clearRect(0,0,canvas.width,canvas.height);
      particles.forEach(p => {
        // Repelir do mouse levemente
        const dx = p.x - mouse.x, dy = p.y - mouse.y;
        const dist = Math.sqrt(dx*dx+dy*dy);
        if (dist < 100) {
          p.vx += dx/dist * .15;
          p.vy += dy/dist * .15;
        }
        p.vx *= .99; p.vy *= .99;
        p.x += p.vx; p.y += p.vy;
        if (p.x < 0) p.x = canvas.width;
        if (p.x > canvas.width) p.x = 0;
        if (p.y < 0) p.y = canvas.height;
        if (p.y > canvas.height) p.y = 0;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI*2);
        ctx.fillStyle = `rgba(${rgb},${p.alpha})`;
        ctx.fill();
      });
      // Linhas entre partículas próximas
      for (let i = 0; i < particles.length; i++) {
        for (let j = i+1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const d  = Math.sqrt(dx*dx+dy*dy);
          if (d < 100) {
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.strokeStyle = `rgba(${rgb},${(1-d/100)*.25})`;
            ctx.lineWidth = .5;
            ctx.stroke();
          }
        }
      }
      requestAnimationFrame(draw);
    }
    draw();
  }

  // ── Cosmos (estrelas cintilantes) ────────────────
  function initCosmos() {
    const canvas = criarCanvas();
    const ctx    = canvas.getContext('2d');
    const stars  = Array.from({length:150}, () => ({
      x: Math.random()*canvas.width, y: Math.random()*canvas.height,
      r: Math.random()*1.8+.3, alpha: Math.random(), pulse: (Math.random()-.5)*.015,
      cor: Math.random() > .8 ? '#a5b4fc' : '#fff'
    }));
    function draw() {
      ctx.clearRect(0,0,canvas.width,canvas.height);
      stars.forEach(s => {
        s.alpha += s.pulse;
        if (s.alpha > 1 || s.alpha < .05) s.pulse = -s.pulse;
        ctx.beginPath(); ctx.arc(s.x,s.y,s.r,0,Math.PI*2);
        ctx.fillStyle = s.cor.replace(')',`,${s.alpha})`).replace('rgb','rgba').replace('#','rgba(').replace(/([0-9a-f]{2})/gi, m => parseInt(m,16)+',').slice(0,-1)+'0)';
        // simplified:
        ctx.globalAlpha = s.alpha;
        ctx.fillStyle   = s.cor;
        ctx.fill();
      });
      ctx.globalAlpha = 1;
      requestAnimationFrame(draw);
    }
    draw();
  }

  // ── Matrix ────────────────────────────────────────
  function initMatrix() {
    const canvas = criarCanvas();
    canvas.style.opacity = '.25';
    const ctx    = canvas.getContext('2d');
    const cols   = Math.floor(canvas.width/14);
    const drops  = Array(cols).fill(0);
    function draw() {
      ctx.fillStyle = 'rgba(0,0,0,.04)'; ctx.fillRect(0,0,canvas.width,canvas.height);
      ctx.fillStyle = '#0f0'; ctx.font = '12px monospace';
      drops.forEach((y,i) => {
        const ch = String.fromCharCode(0x30A0 + Math.random()*96);
        ctx.fillText(ch, i*14, y*14);
        if (y*14 > canvas.height && Math.random() > .975) drops[i] = 0;
        drops[i]++;
      });
      setTimeout(() => requestAnimationFrame(draw), 60);
    }
    draw();
  }

  // ── Fogo ──────────────────────────────────────────
  function initFogo() {
    const canvas = criarCanvas();
    canvas.style.opacity = '.5';
    const ctx    = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height;
    const particles = Array.from({length:80}, () => ({
      x: Math.random()*W, y: H + Math.random()*100,
      vx: (Math.random()-.5)*1.5, vy: -(Math.random()*2+1.5),
      life: Math.random(), decay: Math.random()*.012+.008
    }));
    function draw() {
      ctx.clearRect(0,0,W,H);
      particles.forEach(p => {
        p.x += p.vx; p.y += p.vy; p.life -= p.decay;
        if (p.life <= 0) {
          p.x = Math.random()*W; p.y = H + 20;
          p.life = Math.random()*.8+.2;
          p.vx = (Math.random()-.5)*1.5; p.vy = -(Math.random()*2+1.5);
        }
        const g = ctx.createRadialGradient(p.x,p.y,0,p.x,p.y,12);
        const l = p.life;
        g.addColorStop(0,  `rgba(255,200,50,${l*.9})`);
        g.addColorStop(.4, `rgba(255,100,0,${l*.6})`);
        g.addColorStop(1,  `rgba(255,0,0,0)`);
        ctx.beginPath(); ctx.arc(p.x,p.y,12,0,Math.PI*2);
        ctx.fillStyle = g; ctx.fill();
      });
      requestAnimationFrame(draw);
    }
    draw();
  }

  // ── Chuva ─────────────────────────────────────────
  function initChuva() {
    const canvas = criarCanvas();
    canvas.style.opacity = '.35';
    const ctx    = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height;
    const gotas = Array.from({length:120}, () => ({
      x: Math.random()*W, y: Math.random()*H,
      vel: Math.random()*4+3, len: Math.random()*15+10,
      alpha: Math.random()*.5+.15
    }));
    function draw() {
      ctx.clearRect(0,0,W,H);
      ctx.strokeStyle = 'rgba(147,197,253,.7)';
      gotas.forEach(g => {
        ctx.beginPath();
        ctx.globalAlpha = g.alpha;
        ctx.lineWidth   = .8;
        ctx.moveTo(g.x, g.y);
        ctx.lineTo(g.x+g.len*.15, g.y+g.len);
        ctx.stroke();
        g.y += g.vel;
        if (g.y > H) { g.y = -g.len; g.x = Math.random()*W; }
      });
      ctx.globalAlpha = 1;
      requestAnimationFrame(draw);
    }
    draw();
  }

  // ── Inicializar conforme classe ───────────────────
  document.addEventListener('DOMContentLoaded', () => {
    const efeito = getEfeitoAtivo();
    if (!efeito) return;
    if (efeito === 'efeito-particles-gold')   initParticulas('#fbbf24');
    else if (efeito === 'efeito-particles-purple') initParticulas('#a855f7');
    else if (efeito === 'efeito-particles-blue')   initParticulas('#06b6d4');
    else if (efeito === 'efeito-cosmos')  initCosmos();
    else if (efeito === 'efeito-matrix')  initMatrix();
    else if (efeito === 'efeito-fogo')    initFogo();
    else if (efeito === 'efeito-chuva')   initChuva();
  });

})();
