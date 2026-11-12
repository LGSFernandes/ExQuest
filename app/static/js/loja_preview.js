/* ExQuest — Loja Preview System
   Preview ao vivo de bordas, efeitos e badges antes de comprar */

function abrirPreview(itemId, itemNome, itemTipo, itemCss, itemDescricao) {
  const modal = document.getElementById('preview-modal');
  if (!modal) return;
  document.getElementById('preview-item-nome').textContent = itemNome;
  document.getElementById('preview-item-desc').textContent = itemDescricao;

  const avatarWrap = document.getElementById('preview-avatar-wrap');
  const perfilWrap = document.getElementById('preview-perfil-wrap');

  // Parar efeito anterior
  if (window._particlesPreview) { window._particlesPreview.destroy?.(); window._particlesPreview = null; }

  // Resetar
  avatarWrap.className = 'preview-avatar';
  perfilWrap.innerHTML = '';
  const badgeEl = document.getElementById('preview-badge');
  badgeEl.style.display = 'none';

  if (itemTipo === 'borda') {
    // Aplica borda no avatar
    avatarWrap.classList.add(itemCss);
  } else if (itemTipo === 'efeito') {
    // Efeito fica NO FUNDO (perfilWrap), avatar fica por cima — igual ao perfil real
    iniciarEfeitoPreview(itemCss, perfilWrap);
  } else if (itemTipo === 'badge') {
    badgeEl.className = 'badge ' + itemCss;
    badgeEl.style.display = 'inline-flex';
  }

  modal.classList.add('show');
}

function fecharPreview() {
  document.getElementById('preview-modal')?.classList.remove('show');
  // Parar partículas se houver
  if (window._particlesPreview) {
    window._particlesPreview.destroy?.();
    window._particlesPreview = null;
  }
}

function iniciarEfeitoPreview(css, container) {
  // Limpar canvas anterior
  container.querySelectorAll('canvas').forEach(c => c.remove());
  if (window._particlesPreview) { window._particlesPreview.destroy?.(); window._particlesPreview = null; }

  const canvas = document.createElement('canvas');
  canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none;border-radius:inherit';
  container.style.position = 'relative';
  container.appendChild(canvas);
  const ctx = canvas.getContext('2d');
  canvas.width  = container.offsetWidth  || 300;
  canvas.height = container.offsetHeight || 160;
  const W = canvas.width, H = canvas.height;
  let running = true;
  window._particlesPreview = { destroy: () => { running = false; canvas.remove(); } };

  function makeParticles(r,g,b) {
    const ps = Array.from({length:35},()=>({x:Math.random()*W,y:Math.random()*H,vx:(Math.random()-.5)*.7,vy:(Math.random()-.5)*.7,r:Math.random()*2+.8,a:Math.random()*.6+.2}));
    function f(){if(!running)return;ctx.clearRect(0,0,W,H);ps.forEach(p=>{p.x+=p.vx;p.y+=p.vy;if(p.x<0)p.x=W;if(p.x>W)p.x=0;if(p.y<0)p.y=H;if(p.y>H)p.y=0;ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,Math.PI*2);ctx.fillStyle=`rgba(${r},${g},${b},${p.a})`;ctx.fill();});requestAnimationFrame(f);}
    f();
  }
  function makeStars(){
    const stars=Array.from({length:50},()=>({x:Math.random()*W,y:Math.random()*H,r:Math.random()*1.5+.2,a:Math.random(),p:(Math.random()-.5)*.018}));
    function f(){if(!running)return;ctx.clearRect(0,0,W,H);stars.forEach(s=>{s.a+=s.p;if(s.a>1||s.a<.05)s.p=-s.p;ctx.beginPath();ctx.arc(s.x,s.y,s.r,0,Math.PI*2);ctx.globalAlpha=s.a;ctx.fillStyle='#fff';ctx.fill();});ctx.globalAlpha=1;requestAnimationFrame(f);}
    f();
  }
  function makeMatrix(){
    canvas.style.opacity='.35';
    const cols=Math.floor(W/11),drops=Array(cols).fill(0);
    function f(){if(!running)return;ctx.fillStyle='rgba(0,0,0,.06)';ctx.fillRect(0,0,W,H);ctx.fillStyle='#0f0';ctx.font='9px monospace';drops.forEach((y,i)=>{ctx.fillText(String.fromCharCode(0x30A0+Math.random()*96),i*11,y*11);if(y*11>H&&Math.random()>.975)drops[i]=0;drops[i]++;});setTimeout(()=>{if(running)requestAnimationFrame(f);},80);}
    f();
  }
  function makeFire(){
    const ps=Array.from({length:40},()=>({x:Math.random()*W,y:H+10,vx:(Math.random()-.5),vy:-(Math.random()*1.5+.8),life:Math.random(),decay:.01}));
    function f(){if(!running)return;ctx.clearRect(0,0,W,H);ps.forEach(p=>{p.x+=p.vx;p.y+=p.vy;p.life-=p.decay;if(p.life<=0){p.x=Math.random()*W;p.y=H+5;p.life=Math.random()*.8+.2;p.vx=(Math.random()-.5);p.vy=-(Math.random()*1.5+.8);}const g=ctx.createRadialGradient(p.x,p.y,0,p.x,p.y,9);g.addColorStop(0,`rgba(255,200,50,${p.life*.9})`);g.addColorStop(.4,`rgba(255,80,0,${p.life*.5})`);g.addColorStop(1,'rgba(255,0,0,0)');ctx.beginPath();ctx.arc(p.x,p.y,9,0,Math.PI*2);ctx.fillStyle=g;ctx.fill();});requestAnimationFrame(f);}
    f();
  }
  function makeRain(){
    const ds=Array.from({length:50},()=>({x:Math.random()*W,y:Math.random()*H,v:Math.random()*3+2,l:Math.random()*10+6,a:Math.random()*.4+.1}));
    function f(){if(!running)return;ctx.clearRect(0,0,W,H);ds.forEach(g=>{ctx.beginPath();ctx.globalAlpha=g.a;ctx.strokeStyle='rgba(147,197,253,.9)';ctx.lineWidth=.7;ctx.moveTo(g.x,g.y);ctx.lineTo(g.x+g.l*.1,g.y+g.l);ctx.stroke();g.y+=g.v;if(g.y>H){g.y=-g.l;g.x=Math.random()*W;}});ctx.globalAlpha=1;requestAnimationFrame(f);}
    f();
  }

  if(css==='efeito-particles-gold')   makeParticles(251,191,36);
  else if(css==='efeito-particles-purple') makeParticles(168,85,247);
  else if(css==='efeito-particles-blue')   makeParticles(6,182,212);
  else if(css==='efeito-cosmos')  makeStars();
  else if(css==='efeito-matrix')  makeMatrix();
  else if(css==='efeito-fogo')    makeFire();
  else if(css==='efeito-chuva')   makeRain();
  else makeParticles(99,102,241); // default
}

function criarParticulasPreview(container, cor) {
  const canvas = document.createElement('canvas');
  canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none;border-radius:inherit';
  container.style.position = 'relative';
  container.appendChild(canvas);
  const ctx = canvas.getContext('2d');
  canvas.width  = container.offsetWidth  || 300;
  canvas.height = container.offsetHeight || 150;
  const particles = Array.from({length: 30}, () => ({
    x: Math.random() * canvas.width, y: Math.random() * canvas.height,
    r: Math.random() * 2.5 + 1, vx: (Math.random()-0.5)*0.8, vy: -Math.random()*0.8-0.3,
    alpha: Math.random()
  }));
  let running = true;
  window._particlesPreview = { destroy: () => { running = false; canvas.remove(); } };
  function draw() {
    if (!running) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    particles.forEach(p => {
      p.x += p.vx; p.y += p.vy; p.alpha -= 0.003;
      if (p.y < 0 || p.alpha <= 0) {
        p.x = Math.random() * canvas.width; p.y = canvas.height;
        p.alpha = Math.random() * 0.7 + 0.3; p.vy = -Math.random()*0.8-0.3;
      }
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI*2);
      ctx.fillStyle = cor + Math.floor(p.alpha*255).toString(16).padStart(2,'0');
      ctx.fill();
    });
    requestAnimationFrame(draw);
  }
  draw();
}

function criarEstrelasPreview(container) {
  const canvas = document.createElement('canvas');
  canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none;border-radius:inherit';
  container.style.position = 'relative';
  container.appendChild(canvas);
  const ctx = canvas.getContext('2d');
  canvas.width = container.offsetWidth || 300;
  canvas.height= container.offsetHeight || 150;
  const stars = Array.from({length:40},()=>({
    x:Math.random()*canvas.width, y:Math.random()*canvas.height,
    r:Math.random()*1.5, alpha:Math.random(), pulse: Math.random()*0.02
  }));
  let running = true;
  window._particlesPreview = { destroy: () => { running=false; canvas.remove(); } };
  function draw() {
    if (!running) return;
    ctx.clearRect(0,0,canvas.width,canvas.height);
    stars.forEach(s => {
      s.alpha += s.pulse; if(s.alpha>1||s.alpha<0.1) s.pulse=-s.pulse;
      ctx.beginPath(); ctx.arc(s.x,s.y,s.r,0,Math.PI*2);
      ctx.fillStyle=`rgba(255,255,255,${s.alpha})`; ctx.fill();
    });
    requestAnimationFrame(draw);
  }
  draw();
}

function criarMatrixPreview(container) {
  const canvas = document.createElement('canvas');
  canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none;border-radius:inherit;opacity:.4';
  container.style.position = 'relative';
  container.appendChild(canvas);
  const ctx = canvas.getContext('2d');
  canvas.width = container.offsetWidth || 300;
  canvas.height= container.offsetHeight || 150;
  const cols = Math.floor(canvas.width/12);
  const drops = Array(cols).fill(0);
  let running = true;
  window._particlesPreview = { destroy: () => { running=false; canvas.remove(); } };
  function draw() {
    if (!running) return;
    ctx.fillStyle='rgba(0,0,0,0.05)'; ctx.fillRect(0,0,canvas.width,canvas.height);
    ctx.fillStyle='#0f0'; ctx.font='10px monospace';
    drops.forEach((y,i) => {
      const char = String.fromCharCode(0x30A0+Math.random()*96);
      ctx.fillText(char, i*12, y*12);
      if(y*12>canvas.height && Math.random()>0.975) drops[i]=0;
      drops[i]++;
    });
    setTimeout(()=>requestAnimationFrame(draw), 80);
  }
  draw();
}

// Fechar modal ao clicar fora
document.addEventListener('click', e => {
  if(e.target.id === 'preview-modal') fecharPreview();
});
document.addEventListener('keydown', e => {
  if(e.key === 'Escape') fecharPreview();
});
