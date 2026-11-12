import os, random, string, secrets
from datetime import datetime, timezone, timedelta
from functools import wraps

from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, jsonify, abort, current_app)
from flask_login import login_user, logout_user, login_required, current_user

# pyrefly: ignore [missing-import]
from flask_mail import Message

from app import db, bcrypt, mail
from app.models import (Usuario, Streak, Materia, Questao, Alternativa,
                        RespostaUsuario, ItemLoja, InventarioItem, Amizade,
                        GrupoChat, GrupoMembro, Mensagem, Assinatura,
                        LogAuditoria, ConteudoBloqueado, TokenRecuperacao)
from app.forms import (FormRegistro, FormLogin, FormEditarPerfil, FormAlterarSenha,
                       FormMateria, FormQuestao, FormMensagem, FormGrupo,
                       FormRecuperarSenha, FormRedefinirSenha)
from app.security import (sanitizar_texto, validar_arquivo_imagem,
                          nome_arquivo_seguro, ip_usuario, registrar_log,
                          validar_texto_seguro)

main = Blueprint('main', __name__)

# ════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════

def gerar_tag_unica():
    while True:
        tag = ''.join(random.choices(string.digits, k=5))
        if not Usuario.query.filter_by(tag=tag).first():
            return tag

def admin_required(f):
    @wraps(f)
    def deco(*a, **kw):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*a, **kw)
    return deco

def calcular_recompensa(questao, usuario, nota=1.0):
    xp_min, xp_max = questao.xp_recompensa
    m_min,  m_max = questao.moedas_recompensa
    xp = int(random.randint(xp_min, xp_max) * nota)
    moedas = int(random.randint(m_min, m_max) * nota)
    bxp = usuario.boost_xp_atual
    bm = usuario.boost_moeda_atual
    return int(xp * (1 + bxp/100)), int(moedas * (1 + bm/100))

def salvar_upload(arquivo, pasta, prefixo=''):
    if not arquivo or not arquivo.filename:
        return None
    ok, msg = validar_arquivo_imagem(arquivo)
    if not ok:
        flash(msg, 'danger')
        return None
    nome = nome_arquivo_seguro(arquivo.filename, prefixo)
    base = os.path.join(current_app.root_path, 'static', 'data', pasta)
    os.makedirs(base, exist_ok=True)
    arquivo.save(os.path.join(base, nome))
    return nome

def amigos_ids(uid):
    q = Amizade.query.filter(
        ((Amizade.solicitante_id==uid)|(Amizade.destinatario_id==uid)),
        Amizade.status=='aceito').all()
    ids = set()
    for a in q:
        ids.add(a.destinatario_id if a.solicitante_id==uid else a.solicitante_id)
    return ids

def _avaliar_nlp_gratis(enunciado, resposta_correta, resposta_usuario):
    """
    Avaliação NLP 100% gratuita e local usando técnicas de similaridade textual.
    Não depende de nenhuma API externa paga.
    Usa: TF-IDF cosine similarity + análise semântica básica + heurísticas pedagógicas.
    """
    import re, math

    def normalizar(txt):
        txt = txt.lower().strip()
        txt = re.sub('[^a-zA-Z0-9áéíóúàãõâêîôûçÁÉÍÓÚÀÃÕÂÊÎÔÛÇ ]', ' ', txt)
        return txt

    def tokenizar(txt):
        return [w for w in normalizar(txt).split() if len(w) > 2]

    # Stop words PT-BR básicas
    STOPWORDS = {'que', 'uma', 'para', 'com', 'por', 'como', 'mais', 'mas',
                 'não', 'sim', 'ser', 'ter', 'seu', 'sua', 'dos', 'das',
                 'nos', 'nas', 'pelo', 'pela', 'isso', 'isto', 'esse', 'essa',
                 'ele', 'ela', 'eles', 'elas', 'pode', 'pois', 'também'}

    def filtrar(tokens):
        return [t for t in tokens if t not in STOPWORDS]

    def tf_idf_sim(a, b):
        tokens_a = filtrar(tokenizar(a))
        tokens_b = filtrar(tokenizar(b))
        if not tokens_a or not tokens_b:
            return 0.0
        vocab = list(set(tokens_a) | set(tokens_b))
        def tf(tokens, word):
            return tokens.count(word) / len(tokens) if tokens else 0
        def idf(word):
            docs = sum(1 for t in [tokens_a, tokens_b] if word in t)
            return math.log((2 + 1) / (docs + 1)) + 1
        def vec(tokens):
            return [tf(tokens, w) * idf(w) for w in vocab]
        va, vb = vec(tokens_a), vec(tokens_b)
        dot  = sum(x*y for x,y in zip(va,vb))
        norm = math.sqrt(sum(x*x for x in va)) * math.sqrt(sum(y*y for y in vb))
        return dot / norm if norm else 0.0

    def jaccard(a, b):
        sa = set(filtrar(tokenizar(a)))
        sb = set(filtrar(tokenizar(b)))
        if not sa and not sb: return 0.0
        return len(sa & sb) / len(sa | sb)

    # Calcular similaridades
    sim_cos = tf_idf_sim(resposta_correta, resposta_usuario)
    sim_jac = jaccard(resposta_correta, resposta_usuario)

    # Bônus por conceitos-chave da questão presentes
    tokens_questao = set(filtrar(tokenizar(enunciado)))
    tokens_resp = set(filtrar(tokenizar(resposta_usuario)))
    cobertura_q = len(tokens_questao & tokens_resp) / len(tokens_questao) if tokens_questao else 0

    # Penalidade por resposta muito curta
    len_esperada = len(filtrar(tokenizar(resposta_correta)))
    len_dada = len(filtrar(tokenizar(resposta_usuario)))
    penalidade = max(0.0, 1.0 - max(0, len_esperada - len_dada) / max(len_esperada, 1) * 0.4)

    # Nota composta
    nota = (sim_cos * 0.55 + sim_jac * 0.30 + cobertura_q * 0.15) * penalidade
    nota = round(min(nota, 1.0), 3)

    correto = nota >= 0.55

    # Gerar feedback contextualizado
    if nota >= 0.85:
        feedback = f'Excelente! Sua resposta cobre os principais conceitos com alta precisão ({int(nota*100)}%).'
    elif nota >= 0.70:
        feedback = f'Boa resposta! Você abordou os pontos principais, mas pode aprofundar mais alguns conceitos ({int(nota*100)}%).'
    elif nota >= 0.55:
        feedback = f'Resposta parcialmente correta ({int(nota*100)}%). Revise os conceitos principais da questão.'
    elif nota >= 0.30:
        feedback = f'Sua resposta está no caminho certo, mas faltam elementos importantes ({int(nota*100)}%). Compare com o gabarito.'
    else:
        feedback = f'Resposta muito diferente do esperado ({int(nota*100)}%). Estude o conteúdo e tente novamente.'

    return correto, nota, feedback


def avaliar_discursiva_ia(enunciado, resposta_correta, resposta_usuario):
    """Avalia resposta discursiva com IA 100% gratuita e local (sem API paga)."""
    if not resposta_correta or not resposta_correta.strip():
        # Sem gabarito: aceitar qualquer resposta com tamanho mínimo
        palavras = len(resposta_usuario.split())
        if palavras >= 10:
            return True, 0.7, 'Resposta aceita (sem gabarito configurado). Questão aberta.'
        return False, 0.2, 'Resposta muito curta. Elabore mais sua resposta.'

    try:
        correto, nota, feedback = _avaliar_nlp_gratis(
            enunciado, resposta_correta, resposta_usuario)
        return correto, nota, feedback
    except Exception as e:
        # Fallback mínimo
        palavras_e = set(resposta_correta.lower().split())
        palavras_u = set(resposta_usuario.lower().split())
        if not palavras_e:
            return False, 0.0, 'Sem gabarito configurado.'
        inter = palavras_e & palavras_u
        nota = round(min(len(inter) / len(palavras_e), 1.0), 2)
        return nota >= 0.5, nota, f'Correspondência: {int(nota*100)}%.'


def detectar_uso_ia(tempos_resposta: list, acertos: list) -> dict:
    """
    Analisa padrões de resposta para detectar uso de IA.
    Retorna {'suspeito': bool, 'nivel': str, 'motivos': list}
    Completamente gratuito — análise estatística local.
    """
    import statistics

    if len(tempos_resposta) < 3:
        return {'suspeito': False, 'nivel': 'baixo', 'motivos': []}

    motivos = []
    pontuacao_suspeita = 0

    # 1. Tempo médio muito baixo (< 4 segundos por questão)
    media_tempo = statistics.mean(tempos_resposta)
    if media_tempo < 4:
        motivos.append(f'Tempo médio suspeito: {media_tempo:.1f}s/questão')
        pontuacao_suspeita += 3

    # 2. Variância muito baixa (respostas uniformemente rápidas = bot)
    if len(tempos_resposta) >= 5:
        try:
            dp = statistics.stdev(tempos_resposta)
            if dp < 1.5 and media_tempo < 8:
                motivos.append(f'Padrão de tempo uniforme (DP={dp:.2f}s) — possível automação')
                pontuacao_suspeita += 4
        except statistics.StatisticsError:
            pass

    # 3. Taxa de acerto impossível com velocidade alta
    if acertos and len(acertos) >= 5:
        taxa = sum(acertos) / len(acertos)
        if taxa >= 0.95 and media_tempo < 6:
            motivos.append(f'Taxa de acerto {int(taxa*100)}% com tempo médio {media_tempo:.1f}s')
            pontuacao_suspeita += 5

    # 4. Nenhum tempo < 2s (humanos às vezes são rápidos em questões fáceis)
    min_tempo = min(tempos_resposta)
    if min_tempo > 25 and len(tempos_resposta) >= 5:
        # Todos demorando exatamente entre 25-35s = possível delay artificial
        max_tempo = max(tempos_resposta)
        if max_tempo - min_tempo < 15:
            motivos.append('Todos os tempos em faixa suspeita de delay artificial')
            pontuacao_suspeita += 2

    nivel = 'baixo'
    if pontuacao_suspeita >= 7:
        nivel = 'alto'
    elif pontuacao_suspeita >= 4:
        nivel = 'medio'

    return {
        'suspeito': pontuacao_suspeita >= 4,
        'nivel': nivel,
        'pontuacao': pontuacao_suspeita,
        'motivos': motivos
    }

# ════════════════════════════════════════════
#  AUTH — LOGIN / REGISTRO / GOOGLE / SENHA
# ════════════════════════════════════════════

@main.route('/registro', methods=['GET','POST'])
def registro():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    form = FormRegistro()
    if form.validate_on_submit():
        senha_hash = bcrypt.generate_password_hash(form.senha.data).decode('utf-8')
        tag        = gerar_tag_unica()
        u = Usuario(
            # pyrefly: ignore [unexpected-keyword]
            nome=sanitizar_texto(form.nome.data,80),
            # pyrefly: ignore [unexpected-keyword]
            sobrenome=sanitizar_texto(form.sobrenome.data,80),
            # pyrefly: ignore [unexpected-keyword]
            username=form.username.data.strip().lower(),
            # pyrefly: ignore [unexpected-keyword]
            email=form.email.data.strip().lower(),
            # pyrefly: ignore [unexpected-keyword]
            senha_hash=senha_hash, 
            # pyrefly: ignore [unexpected-keyword]
            tag=tag,
        )
        db.session.add(u)
        db.session.flush()
        # pyrefly: ignore [unexpected-keyword]
        db.session.add(Streak(usuario_id=u.id))
        registrar_log(db.session,'registro',u.id,ip=ip_usuario(request))
        db.session.commit()
        login_user(u)
        flash('Conta criada! Bem-vindo ao ExQuest \U0001F3AF','success')
        return redirect(url_for('main.dashboard'))
    return render_template('registro.html', form=form, titulo='Criar Conta')

# Simple in-memory brute-force protection
import time as _time
_login_attempts: dict = {}  # ip -> [timestamps]

@main.route('/login', methods=['GET','POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    form = FormLogin()
    client_ip = ip_usuario(request)

    # Rate limit: max 10 attempts per 10 minutes per IP
    now = _time.time()
    window = 600  # 10 min
    max_att = 10
    attempts = _login_attempts.get(client_ip, [])
    attempts = [t for t in attempts if now - t < window]
    if len(attempts) >= max_att:
        wait = int(window - (now - attempts[0]))
        flash(f'Muitas tentativas de login. Aguarde {wait}s.', 'danger')
        return render_template('login.html', form=form, titulo='Entrar')

    if form.validate_on_submit():
        u = Usuario.query.filter_by(email=form.email.data.lower()).first()
        if u and not u.is_banido and u.senha_hash and bcrypt.check_password_hash(u.senha_hash, form.senha.data):
            # Clear attempts on success
            _login_attempts.pop(client_ip, None)
            login_user(u, remember=form.lembrar.data)
            registrar_log(db.session,'login',u.id,ip=client_ip)
            db.session.commit()
            flash(f'Bem-vindo de volta, {u.nome}!','success')
            return redirect(request.args.get('next') or url_for('main.dashboard'))
        # Record failed attempt
        attempts.append(now)
        _login_attempts[client_ip] = attempts
        registrar_log(db.session,'login_falha',detalhe=form.email.data,
                      ip=client_ip,resultado='bloqueado')
        db.session.commit()
        flash('Email ou senha incorretos.','danger')
    return render_template('login.html', form=form, titulo='Entrar')

@main.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu da sua conta.','info')
    return redirect(url_for('main.login'))

# ── Google OAuth ─────────────────────────────────────

@main.route('/auth/google')
def google_login():
    from authlib.integrations.flask_client import OAuth  # pyright: ignore[reportMissingImports]
    oauth = OAuth(current_app)
    google = oauth.register(
        name='google',
        client_id=os.getenv('GOOGLE_CLIENT_ID'),
        client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope':'openid email profile'},
    )
    redirect_uri = url_for('main.google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@main.route('/auth/google/callback')
def google_callback():
    from authlib.integrations.flask_client import OAuth  # pyright: ignore[reportMissingImports]
    oauth = OAuth(current_app)
    google = oauth.register(
        name='google',
        client_id=os.getenv('GOOGLE_CLIENT_ID'),
        client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope':'openid email profile'},
    )
    try:
        token    = google.authorize_access_token()
        userinfo = token.get('userinfo') or google.userinfo()
        email    = userinfo['email']
        nome     = userinfo.get('given_name','Usuário')
        sobrenome= userinfo.get('family_name','')
        google_id= userinfo['sub']

        u = Usuario.query.filter_by(google_id=google_id).first()
        if not u:
            u = Usuario.query.filter_by(email=email).first()
        if not u:
            tag = gerar_tag_unica()
            base_user = email.split('@')[0][:30].lower()
            username  = base_user
            c = 1
            while Usuario.query.filter_by(username=username).first():
                username = f'{base_user}{c}'; c += 1
            u = Usuario(
                # pyrefly: ignore [unexpected-keyword]
                nome=sanitizar_texto(nome,80),
                # pyrefly: ignore [unexpected-keyword]
                sobrenome=sanitizar_texto(sobrenome,80),
                # pyrefly: ignore [unexpected-keyword]
                username=username,
                # pyrefly: ignore [unexpected-keyword]
                email=email,
                # pyrefly: ignore [unexpected-keyword]
                senha_hash=None,
                # pyrefly: ignore [unexpected-keyword]
                tag=tag,
                # pyrefly: ignore [unexpected-keyword]
                google_id=google_id,
            )
            db.session.add(u)
            db.session.flush()
            # pyrefly: ignore [unexpected-keyword]
            db.session.add(Streak(usuario_id=u.id))
        else:
            u.google_id = google_id
        db.session.commit()
        login_user(u)
        flash(f'Bem-vindo, {u.nome}! \U0001F3AF','success')
        return redirect(url_for('main.dashboard'))
    except Exception as e:
        flash('Erro ao autenticar com Google. Tente novamente.','danger')
        return redirect(url_for('main.login'))

# ── Recuperação de senha ─────────────────────────────

@main.route('/recuperar-senha', methods=['GET','POST'])
def recuperar_senha():
    form = FormRecuperarSenha()
    if form.validate_on_submit():
        u = Usuario.query.filter_by(email=form.email.data.lower()).first()
        if u and u.senha_hash:
            # Invalidar tokens anteriores
            TokenRecuperacao.query.filter_by(usuario_id=u.id, usado=False).update({'usado':True})
            token_str = secrets.token_urlsafe(48)
            expira = datetime.now(timezone.utc) + timedelta(hours=2)
            # pyrefly: ignore [unexpected-keyword]
            db.session.add(TokenRecuperacao(usuario_id=u.id, token=token_str, expira=expira))
            db.session.commit()
            link = url_for('main.redefinir_senha', token=token_str, _external=True)
            try:
                msg = Message('Recuperação de Senha — ExQuest',
                              recipients=[u.email])
                msg.html = f"""
                <div style="font-family:sans-serif;max-width:520px;margin:0 auto;background:#07090f;color:#f1f5f9;padding:32px;border-radius:16px">
                  <h2 style="color:#818cf8">ExQuest \U0001F3AF — Recuperar Senha</h2>
                  <p>Olá, <strong>{u.nome}</strong>! Recebemos uma solicitação para redefinir sua senha.</p>
                  <p>Clique no botão abaixo (válido por 2 horas):</p>
                  <a href="{link}" style="display:inline-block;background:linear-gradient(135deg,#6366f1,#7c3aed);color:#fff;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:700;margin:16px 0">
                    Redefinir Senha
                  </a>
                  <p style="color:#94a3b8;font-size:13px">Se não foi você, ignore este email.</p>
                  <p style="color:#475569;font-size:11px">Link: {link}</p>
                </div>"""
                mail.send(msg)
            except Exception:
                pass  # Email configurado mas falhou — link ainda funciona
        # Sempre mostrar mesma mensagem por segurança
        flash('Se o email existir, você receberá as instruções em instantes.','info')
        return redirect(url_for('main.login'))
    return render_template('recuperar_senha.html', form=form, titulo='Recuperar Senha')

@main.route('/redefinir-senha/<token>', methods=['GET','POST'])
def redefinir_senha(token):
    tr = TokenRecuperacao.query.filter_by(token=token).first()
    if not tr or not tr.valido:
        flash('Link inválido ou expirado.','danger')
        return redirect(url_for('main.login'))
    form = FormRedefinirSenha()
    if form.validate_on_submit():
        tr.usuario.senha_hash = bcrypt.generate_password_hash(form.nova_senha.data).decode('utf-8')
        tr.usado = True
        db.session.commit()
        flash('Senha redefinida com sucesso! Faça login.','success')
        return redirect(url_for('main.login'))
    return render_template('redefinir_senha.html', form=form, titulo='Nova Senha')

# ════════════════════════════════════════════
#  DASHBOARD
# ════════════════════════════════════════════

@main.route('/')
@main.route('/dashboard')
@login_required
def dashboard():
    materias = Materia.query.all()
    streak = current_user.streak
    ultimas = (RespostaUsuario.query.filter_by(usuario_id=current_user.id)
                .order_by(RespostaUsuario.data_resposta.desc()).limit(5).all())
    ranking = Usuario.query.order_by(Usuario.xp.desc()).limit(5).all()
    stats_m = []
    for m in materias:
        ids = [q.id for q in m.questoes.all()]
        if not ids: continue
        total = RespostaUsuario.query.filter(
            RespostaUsuario.usuario_id==current_user.id,
            RespostaUsuario.questao_id.in_(ids)).count()
        acerto = RespostaUsuario.query.filter(
            RespostaUsuario.usuario_id==current_user.id,
            RespostaUsuario.questao_id.in_(ids),
            RespostaUsuario.acertou==True).count()
        stats_m.append({'materia':m,'total':total,'acertos':acerto,
                        'pct':round(acerto/total*100,1) if total else 0})
    # Verificar oferta trial
    tem_trial = False
    try:
        tem_trial = verificar_oferta_trial(current_user)
    except Exception:
        pass

    # Verificar recompensa de nível pendente
    recompensa_nivel_dash = None
    try:
        from app.models import RECOMPENSAS_NIVEL, RecompensaNivelConcedida
        for nivel_r in sorted(RECOMPENSAS_NIVEL.keys()):
            if current_user.nivel >= nivel_r:
                ja = RecompensaNivelConcedida.query.filter_by(
                    usuario_id=current_user.id, nivel=nivel_r).first()
                if not ja:
                    recompensa_nivel_dash = _verificar_recompensa_nivel(current_user, nivel_r)
                    db.session.commit()
                    break
    except Exception:
        pass

    return render_template('dashboard.html', materias=materias, streak=streak,
                           ultimas_respostas=ultimas, ranking=ranking,
                           stats_materias=stats_m, tem_trial=tem_trial,
                           recompensa_nivel=recompensa_nivel_dash,
                           titulo='Dashboard')

# ════════════════════════════════════════════
#  PERFIL
# ════════════════════════════════════════════

@main.route('/perfil/<username>')
@login_required
def perfil(username):
    u = Usuario.query.filter_by(username=username).first_or_404()
    eh_proprio = (u.id == current_user.id)
    status_amizade = sou_solicitante = amizade_id = None
    if not eh_proprio:
        rel = Amizade.query.filter(
            ((Amizade.solicitante_id==current_user.id)&(Amizade.destinatario_id==u.id))|
            ((Amizade.solicitante_id==u.id)&(Amizade.destinatario_id==current_user.id))
        ).first()
        status_amizade = rel.status if rel else None
        amizade_id = rel.id if rel else None
        sou_solicitante = rel and rel.solicitante_id == current_user.id
    ultimas = []
    if eh_proprio or u.mostrar_historico:
        ultimas = (RespostaUsuario.query.filter_by(usuario_id=u.id)
                   .order_by(RespostaUsuario.data_resposta.desc()).limit(10).all())
    dados_grafico = None
    if eh_proprio or u.mostrar_stats:
        dados_grafico = _gerar_dados_grafico(u.id)
    amigos = []
    if eh_proprio or u.mostrar_amigos:
        ids = amigos_ids(u.id)
        amigos = Usuario.query.filter(Usuario.id.in_(ids)).limit(12).all() if ids else []
    return render_template('perfil.html', usuario=u, ultimas_respostas=ultimas,
                           dados_grafico=dados_grafico, amigos=amigos,
                           status_amizade=status_amizade, amizade_id=amizade_id,
                           sou_solicitante=sou_solicitante, eh_proprio=eh_proprio,
                           titulo=f'Perfil de {u.nome}')

def _gerar_dados_grafico(uid):
    from sqlalchemy import func
    from datetime import date as d_type, timedelta as td
    materias = Materia.query.all()
    por_materia = []
    for m in materias:
        ids = [q.id for q in m.questoes.all()]
        if not ids: continue
        total = RespostaUsuario.query.filter(
            RespostaUsuario.usuario_id==uid, RespostaUsuario.questao_id.in_(ids)).count()
        acerto = RespostaUsuario.query.filter(
            RespostaUsuario.usuario_id==uid, RespostaUsuario.questao_id.in_(ids),
            RespostaUsuario.acertou==True).count()
        if total:
            por_materia.append({'nome':m.nome,'cor':m.cor,'acertos':acerto,
                                'erros':total-acerto,'total':total,
                                'pct':round(acerto/total*100,1)})
    ultimos_7 = []
    for i in range(6,-1,-1):
        dia = d_type.today() - td(days=i)
        tot = RespostaUsuario.query.filter(
            RespostaUsuario.usuario_id==uid,
            func.date(RespostaUsuario.data_resposta)==dia).count()
        ace = RespostaUsuario.query.filter(
            RespostaUsuario.usuario_id==uid, RespostaUsuario.acertou==True,
            func.date(RespostaUsuario.data_resposta)==dia).count()
        ultimos_7.append({'dia':dia.strftime('%d/%m'),'total':tot,'acertos':ace})
    return {'por_materia':por_materia,'ultimos_7':ultimos_7}

@main.route('/perfil/editar', methods=['GET','POST'])
@login_required
def editar_perfil():
    form = FormEditarPerfil()
    if form.validate_on_submit():
        current_user.nome = sanitizar_texto(form.nome.data,80)
        current_user.sobrenome = sanitizar_texto(form.sobrenome.data,80)
        current_user.biografia = sanitizar_texto(form.biografia.data or '',300)
        current_user.estilo_perfil = form.estilo_perfil.data
        current_user.mostrar_stats = form.mostrar_stats.data
        current_user.mostrar_historico = form.mostrar_historico.data
        current_user.mostrar_amigos = form.mostrar_amigos.data
        current_user.bloquear_pedidos_amizade = form.bloquear_pedidos_amizade.data

        # Tag customizada (Advan)
        if current_user.pode_tag_custom and form.tag_custom.data:
            nova_tag = form.tag_custom.data.strip()
            conflito = Usuario.query.filter(
                Usuario.tag_custom==nova_tag,
                Usuario.id!=current_user.id).first()
            if not conflito:
                current_user.tag_custom = nova_tag
            else:
                flash('Essa tag já está em uso.','warning')

        # Cor/gradiente/fonte do nick
        if current_user.pode_nick_cor:
            current_user.nick_cor = form.nick_cor.data or None
        if current_user.pode_nick_gradiente:
            current_user.nick_gradiente = form.nick_gradiente.data or None
        if current_user.pode_nick_fonte:
            current_user.nick_fonte = form.nick_fonte.data or None

        # Icon upload
        if form.icon_file.data and form.icon_file.data.filename:
            nome = salvar_upload(form.icon_file.data,'icon','ic_')
            if nome: current_user.icon_path = nome
        elif form.remover_icon.data:
            current_user.icon_path = None
        else:
            current_user.icon_emoji = form.icon_emoji.data

        # Banner upload
        if form.banner_file.data and form.banner_file.data.filename:
            if current_user.pode_upload_banner:
                nome = salvar_upload(form.banner_file.data,'banner','bn_')
                if nome: current_user.banner_path = nome
            else:
                flash('Banner personalizado requer Premium Intermediário+.','warning')
        elif form.remover_banner.data:
            current_user.banner_path = None

        db.session.commit()
        flash('Perfil atualizado!','success')
        return redirect(url_for('main.perfil', username=current_user.username))

    elif request.method == 'GET':
        form.nome.data = current_user.nome
        form.sobrenome.data = current_user.sobrenome
        form.biografia.data = current_user.biografia
        form.icon_emoji.data = current_user.icon_emoji or 'avatar_1'
        form.estilo_perfil.data = current_user.estilo_perfil
        form.mostrar_stats.data = current_user.mostrar_stats
        form.mostrar_historico.data = current_user.mostrar_historico
        form.mostrar_amigos.data = current_user.mostrar_amigos
        form.bloquear_pedidos_amizade.data = current_user.bloquear_pedidos_amizade
        form.nick_cor.data = current_user.nick_cor or ''
        form.nick_gradiente.data = current_user.nick_gradiente or ''
        form.nick_fonte.data = current_user.nick_fonte or ''
        form.tag_custom.data = current_user.tag_custom or ''
    return render_template('editar_perfil.html', form=form, titulo='Editar Perfil')

@main.route('/perfil/remover-icon', methods=['POST'])
@login_required
def remover_icon():
    current_user.icon_path = None
    db.session.commit()
    return jsonify({'ok':True})

@main.route('/perfil/remover-banner', methods=['POST'])
@login_required
def remover_banner():
    current_user.banner_path = None
    db.session.commit()
    return jsonify({'ok':True})

@main.route('/perfil/senha', methods=['GET','POST'])
@login_required
def alterar_senha():
    form = FormAlterarSenha()
    if form.validate_on_submit():
        if current_user.senha_hash and bcrypt.check_password_hash(current_user.senha_hash, form.senha_atual.data):
            current_user.senha_hash = bcrypt.generate_password_hash(form.nova_senha.data).decode('utf-8')
            db.session.commit()
            flash('Senha alterada!','success')
            return redirect(url_for('main.perfil', username=current_user.username))
        flash('Senha atual incorreta.','danger')
    return render_template('alterar_senha.html', form=form, titulo='Alterar Senha')

# ════════════════════════════════════════════
#  QUESTÕES AVULSAS
# ════════════════════════════════════════════

@main.route('/questoes', methods=['GET'])
@login_required
def questoes():
    from flask import session as flask_session
    from app.models import QuestaoRespondidaSessao
    materias = Materia.query.order_by(Materia.nome).all()
    materia_ids = request.args.getlist('materia_id', type=int)
    dificuldades = request.args.getlist('dificuldade')
    conteudo = request.args.get('conteudo','').strip()
    tipo_q = request.args.get('tipo','')
    sessao_id = request.args.get('sessao_id', '')

    # Inicializar sessão de questões se não existir
    if not sessao_id:
        import uuid
        sessao_id = str(uuid.uuid4())[:16]

    questao = None
    if materia_ids:
        q = Questao.query
        if materia_ids:
            q = q.filter(Questao.materia_id.in_(materia_ids))
        if dificuldades:
            q = q.filter(Questao.dificuldade.in_(dificuldades))
        if conteudo:
            q = q.filter(Questao.conteudo.ilike(f'%{conteudo}%'))
        if tipo_q:
            q = q.filter_by(tipo=tipo_q)

        # Excluir questões já respondidas nesta sessão
        respondidas_ids = [r.questao_id for r in
            QuestaoRespondidaSessao.query.filter_by(
                usuario_id=current_user.id, sessao_id=sessao_id).all()]
        if respondidas_ids:
            q = q.filter(~Questao.id.in_(respondidas_ids))

        if q.count() > 0:
            questao = q.order_by(db.func.random()).first()

    return render_template('questoes/index.html', materias=materias, questao=questao,
                           materia_ids=materia_ids, dificuldades=dificuldades,
                           conteudo=conteudo, tipo_q=tipo_q,
                           sessao_id=sessao_id, titulo='Questões')

# ════════════════════════════════════════════
#  SIMULADOS
# ════════════════════════════════════════════

@main.route('/simulado')
@login_required
def simulado_escolher():
    materias = Materia.query.filter(Materia.questoes.any()).all()
    return render_template('simulado_escolher.html', materias=materias, titulo='Simulados')

@main.route('/simulado/iniciar')
@login_required
def simulado_iniciar():
    if not current_user.pode_fazer_simulado():
        lim = current_user.limite_simulados_dia
        flash(f'Limite de {lim} simulados/dia atingido. Upgrade Premium!','warning')
        return redirect(url_for('main.simulado_escolher'))
    materia_ids = request.args.getlist('materia_id', type=int)
    dificuldades = request.args.getlist('dificuldade')
    conteudo = request.args.get('conteudo','').strip()
    tipo_q = request.args.get('tipo','')
    max_q = current_user.max_questoes_simulado
    quantidade = min(int(request.args.get('quantidade', 10)), max_q)
    tempo_min = quantidade * 2

    q_query = Questao.query
    if materia_ids: q_query = q_query.filter(Questao.materia_id.in_(materia_ids))
    if dificuldades: q_query = q_query.filter(Questao.dificuldade.in_(dificuldades))
    if conteudo: q_query = q_query.filter(Questao.conteudo.ilike(f'%{conteudo}%'))
    if tipo_q: q_query = q_query.filter_by(tipo=tipo_q)

    if q_query.count() == 0:
        flash('Nenhuma questão encontrada com esses filtros.','warning')
        return redirect(url_for('main.simulado_escolher'))

    questoes = q_query.order_by(db.func.random()).limit(quantidade).all()
    current_user.simulados_hoje += 1
    db.session.commit()

    materias_sel = Materia.query.filter(Materia.id.in_(materia_ids)).all() if materia_ids else []
    return render_template('simulado.html', questoes=questoes, materias_sel=materias_sel,
                           tempo_min=tempo_min, max_q=max_q, titulo='Simulado')

# ── API Responder (múltipla escolha) ─────────────────

@main.route('/api/responder', methods=['POST'])
@login_required
def api_responder():
    data = request.get_json()
    if not data: return jsonify({'erro':'Dados inválidos.'}),400
    questao_id = data.get('questao_id')
    alternativa_id = data.get('alternativa_id')
    modo = data.get('modo','questao')
    if not questao_id or not alternativa_id:
        return jsonify({'erro':'Campos ausentes.'}),400
    questao = Questao.query.get(questao_id)
    alternativa = Alternativa.query.get(alternativa_id)
    if not questao or not alternativa or alternativa.questao_id != questao.id:
        return jsonify({'erro':'Dados inválidos.'}),404
    if modo=='questao' and not current_user.pode_responder_questao():
        return jsonify({'erro':f'Limite de {current_user.limite_questoes_dia} questões/dia atingido.','limite':True}),429
    acertou = alternativa.correta
    # ── Anti-cheat: tempo de resposta ──
    tempo_resp = float(data.get('tempo_segundos', 10) or 10)
    if tempo_resp < 1.5:
        registrar_log(db.session, 'resposta_suspeita', current_user.id,
                      detalhe=f'tempo={tempo_resp:.1f}s q={questao_id}',
                      ip=ip_usuario(request), resultado='suspeito')
    # A cada 10 respostas, analisar padrão
    if current_user.total_respostas > 0 and current_user.total_respostas % 10 == 0:
        ultimas = (RespostaUsuario.query.filter_by(usuario_id=current_user.id)
                   .order_by(RespostaUsuario.data_resposta.desc()).limit(10).all())
        if len(ultimas) >= 5:
            tempos_est = [abs((ultimas[i].data_resposta - ultimas[i+1].data_resposta).total_seconds())
                          for i in range(len(ultimas)-1)
                          if 0 < abs((ultimas[i].data_resposta - ultimas[i+1].data_resposta).total_seconds()) < 300]
            acertos_lst = [r.acertou for r in ultimas]
            if tempos_est:
                resultado_ia = detectar_uso_ia(tempos_est, acertos_lst)
                if resultado_ia['suspeito']:
                    registrar_log(db.session, 'uso_ia_detectado', current_user.id,
                                  detalhe='; '.join(resultado_ia.get('motivos',[])),
                                  ip=ip_usuario(request), resultado='suspeito')
                    if resultado_ia.get('pontuacao', 0) >= 10:
                        current_user.is_banido = True
                        db.session.commit()
                        return jsonify({'erro': 'Conta suspensa por uso de automação.'}), 403
    xp_ganho = moedas_ganhas = 0
    if acertou:
        xp_ganho, moedas_ganhas = calcular_recompensa(questao, current_user)
        current_user.xp += xp_ganho
        current_user.moedas += moedas_ganhas
        if current_user.streak: current_user.streak.atualizar()
    if modo=='questao': current_user.questoes_hoje += 1

    # Registrar na sessão (para não repetir)
    sessao_id = data.get('sessao_id', '')
    if sessao_id:
        from app.models import QuestaoRespondidaSessao
        db.session.add(QuestaoRespondidaSessao(
            # pyrefly: ignore [unexpected-keyword]
            usuario_id=current_user.id,
            # pyrefly: ignore [unexpected-keyword]
            questao_id=questao.id,
            # pyrefly: ignore [unexpected-keyword]
            sessao_id=sessao_id))

    nivel_antes = current_user.nivel
    db.session.add(RespostaUsuario(
        # pyrefly: ignore [unexpected-keyword]
        usuario_id=current_user.id, 
        # pyrefly: ignore [unexpected-keyword]
        questao_id=questao.id,
        # pyrefly: ignore [unexpected-keyword]
        alternativa_id=alternativa.id, 
        # pyrefly: ignore [unexpected-keyword]
        acertou=acertou,
        # pyrefly: ignore [unexpected-keyword]
        xp_ganho=xp_ganho, 
        # pyrefly: ignore [unexpected-keyword]
        moedas_ganhas=moedas_ganhas, 
        # pyrefly: ignore [unexpected-keyword]
        modo=modo))
    db.session.flush()

    # Verificar recompensa de nível
    recompensa_nivel = None
    nivel_atual = current_user.nivel
    if nivel_atual > nivel_antes:
        recompensa_nivel = _verificar_recompensa_nivel(current_user, nivel_atual)

    db.session.commit()
    correta = questao.alternativa_correta
    return jsonify({
        'acertou':acertou,'xp_ganho':xp_ganho,'moedas_ganhas':moedas_ganhas,
        'xp_total':current_user.xp,'moedas_total':current_user.moedas,
        'nivel':current_user.nivel,'progresso_nivel':current_user.progresso_nivel,
        'alternativa_correta_id':correta.id if correta else None,
        'explicacao':questao.explicacao or '',
        'streak':current_user.streak.sequencia_atual if current_user.streak else 0,
        'questoes_hoje':current_user.questoes_hoje,
        'limite_questoes':current_user.limite_questoes_dia,
        'recompensa_nivel': recompensa_nivel,
    })

# ── API Responder discursiva ──────────────────────────

@main.route('/api/responder-discursiva', methods=['POST'])
@login_required
def api_responder_discursiva():
    data = request.get_json()
    if not data: return jsonify({'erro':'Dados inválidos.'}),400
    questao_id = data.get('questao_id')
    resp_texto = sanitizar_texto(data.get('resposta_texto',''),2000)
    modo = data.get('modo','questao')
    if not questao_id or not resp_texto.strip():
        return jsonify({'erro':'Questão ou resposta ausente.'}),400
    questao = Questao.query.get(questao_id)
    if not questao or questao.tipo != 'discursiva':
        return jsonify({'erro':'Questão inválida.'}),404
    ok, nota, motivo = validar_texto_seguro(resp_texto)
    if not ok:
        return jsonify({'erro':'Conteúdo inapropriado detectado.'}),400
    if modo=='questao' and not current_user.pode_responder_questao():
        return jsonify({'erro':'Limite diário atingido.','limite':True}),429

    acertou, nota_ia, feedback = avaliar_discursiva_ia(
        questao.enunciado,
        questao.resposta_correta or '(sem gabarito)',
        resp_texto)

    xp_ganho = moedas_ganhas = 0
    if acertou:
        xp_ganho, moedas_ganhas = calcular_recompensa(questao, current_user, nota_ia)
        current_user.xp     += xp_ganho
        current_user.moedas += moedas_ganhas
        if current_user.streak: current_user.streak.atualizar()
    if modo=='questao': current_user.questoes_hoje += 1
    db.session.add(RespostaUsuario(
        # pyrefly: ignore [unexpected-keyword]
        usuario_id=current_user.id, 
        # pyrefly: ignore [unexpected-keyword]
        questao_id=questao.id,
        # pyrefly: ignore [unexpected-keyword]
        resposta_texto=resp_texto, 
        # pyrefly: ignore [unexpected-keyword]
        acertou=acertou,
        # pyrefly: ignore [unexpected-keyword]
        feedback_ia=feedback, 
        # pyrefly: ignore [unexpected-keyword]
        nota_ia=nota_ia,
        # pyrefly: ignore [unexpected-keyword]
        xp_ganho=xp_ganho, 
        # pyrefly: ignore [unexpected-keyword]
        moedas_ganhas=moedas_ganhas, 
        # pyrefly: ignore [unexpected-keyword]
        modo=modo))
    db.session.commit()
    return jsonify({
        'acertou':acertou,'nota_ia':round(nota_ia*100),'feedback':feedback,
        'xp_ganho':xp_ganho,'moedas_ganhas':moedas_ganhas,
        'xp_total':current_user.xp,'moedas_total':current_user.moedas,
        'nivel':current_user.nivel,'progresso_nivel':current_user.progresso_nivel,
        'explicacao':questao.explicacao or '',
        'streak':current_user.streak.sequencia_atual if current_user.streak else 0,
    })

# ════════════════════════════════════════════
#  RANKING
# ════════════════════════════════════════════

@main.route('/ranking')
@login_required
def ranking():
    materia_id = request.args.get('materia_id', type=int)
    page = max(1, min(1000, request.args.get('page', 1, type=int)))
    per_page = 15
    materias_all= Materia.query.order_by(Materia.nome).all()

    if materia_id:
        materia = Materia.query.get_or_404(materia_id)
        ids_q = [q.id for q in materia.questoes.all()]
        from sqlalchemy import func
        sub = (db.session.query(
                RespostaUsuario.usuario_id,
                func.sum(db.cast(RespostaUsuario.acertou,db.Integer)).label('pts'))
               .filter(RespostaUsuario.questao_id.in_(ids_q))
               .group_by(RespostaUsuario.usuario_id)
               .order_by(db.text('pts DESC')).subquery())
        total_users = db.session.query(func.count()).select_from(sub).scalar() or 0
        rows = (db.session.query(Usuario, sub.c.pts)
                .join(sub, Usuario.id == sub.c.usuario_id)
                .order_by(sub.c.pts.desc())
                .offset((page-1)*per_page).limit(per_page).all())
        usuarios = [u for u,_ in rows]
        pts_map = {u.id: p for u,p in rows}
        # Global position of current user
        all_ids = [r[0].id for r in db.session.query(Usuario.id).join(sub, Usuario.id==sub.c.usuario_id).order_by(sub.c.pts.desc()).all()]
        posicao = next((i+1 for i,uid in enumerate(all_ids) if uid==current_user.id), None)
    else:
        materia = None; pts_map = {}
        total_users = Usuario.query.count()
        usuarios = (Usuario.query.order_by(Usuario.xp.desc())
                    .offset((page-1)*per_page).limit(per_page).all())
        all_ids = [u.id for u in Usuario.query.order_by(Usuario.xp.desc()).with_entities(Usuario.id).all()]
        posicao = next((i+1 for i,uid in enumerate(all_ids) if uid==current_user.id), None)

    total_pages = min(1000, max(1, (total_users + per_page - 1) // per_page))
    offset = (page - 1) * per_page  # rank offset for display

    return render_template('ranking.html', usuarios=usuarios, posicao_atual=posicao,
                           materia=materia, materias_all=materias_all,
                           materia_id=materia_id, pts_map=pts_map,
                           page=page, total_pages=total_pages, offset=offset,
                           titulo='Ranking')

# ════════════════════════════════════════════
#  LOJA
# ════════════════════════════════════════════

@main.route('/loja')
@login_required
def loja():
    tipo = request.args.get('tipo','')
    itens = ItemLoja.query.filter_by(ativo=True)
    if tipo: itens = itens.filter_by(tipo=tipo)
    itens = itens.order_by(ItemLoja.raridade.desc(), ItemLoja.preco).all()
    inv_ids = {i.item_id for i in current_user.inventario.all()}
    return render_template('loja/index.html', itens=itens, inv_ids=inv_ids,
                           tipo_filtro=tipo, titulo='Loja')

@main.route('/loja/comprar/<int:item_id>', methods=['POST'])
@login_required
def loja_comprar(item_id):
    item = ItemLoja.query.get_or_404(item_id)
    if not item.ativo: return jsonify({'erro':'Item indisponível.'}),400
    if current_user.moedas < item.preco: return jsonify({'erro':'Moedas insuficientes.'}),400
    inv = InventarioItem.query.filter_by(usuario_id=current_user.id,item_id=item.id).first()
    # Borda, efeito e badge são compráveis apenas uma vez
    if item.tipo in ('borda','efeito','badge') and inv:
        return jsonify({'erro':'Você já possui este item.'}),400
    current_user.moedas -= item.preco
    if inv: inv.quantidade += 1
    # pyrefly: ignore [unexpected-keyword]
    else: db.session.add(InventarioItem(usuario_id=current_user.id,item_id=item.id))
    db.session.commit()
    return jsonify({'ok':True,'moedas':current_user.moedas,'item':item.nome})

@main.route('/loja/usar/<int:item_id>', methods=['POST'])
@login_required
def loja_usar(item_id):
    inv = InventarioItem.query.filter_by(usuario_id=current_user.id,item_id=item_id).first_or_404()
    item = inv.item
    if item.tipo=='borda': current_user.borda_ativa = item.css_class
    elif item.tipo=='efeito': current_user.efeito_ativo = item.css_class
    elif item.tipo=='badge': current_user.badge_ativa = item.css_class
    elif item.tipo=='boost_xp':
        current_user.boost_xp_pct = item.valor_boost
        current_user.boost_xp_expira = datetime.now(timezone.utc)+timedelta(hours=item.duracao_h)
        inv.quantidade -= 1
        if inv.quantidade<=0: db.session.delete(inv)
    elif item.tipo=='boost_moeda':
        current_user.boost_coin_pct = item.valor_boost
        current_user.boost_coin_expira = datetime.now(timezone.utc)+timedelta(hours=item.duracao_h)
        inv.quantidade -= 1
        if inv.quantidade<=0: db.session.delete(inv)
    elif item.tipo=='streak_shield':
        if current_user.streak: current_user.streak.streak_protegido = True
        inv.quantidade -= 1
        if inv.quantidade<=0: db.session.delete(inv)
    db.session.commit()
    return jsonify({'ok':True,'msg':f'{item.nome} ativado!'})

@main.route('/inventario')
@login_required
def inventario():
    itens = (InventarioItem.query.filter_by(usuario_id=current_user.id)
             .join(ItemLoja).order_by(ItemLoja.tipo,ItemLoja.raridade.desc()).all())
    return render_template('loja/inventario.html', itens=itens, titulo='Inventário')

# ════════════════════════════════════════════
#  PREMIUM
# ════════════════════════════════════════════

PLANOS = {
    'basic': {
        'nome': 'Básico', 'mensal': 9.90, 'anual': 94.90, 'cor': '#94a3b8', 'icone': 'basic',
        'beneficios': [
            ('15 questões/dia · 3 simulados/dia (até 15 questões)', None),
            ('GIF como foto de perfil', None),
            ('Boost XP e Moedas +10%', None),
            ('50 amigos · 20 grupos', None),
            ('badge', 'premium_basic'),
        ]
    },
    'inter': {
        'nome': 'Intermediário', 'mensal': 19.90, 'anual': 179.90, 'cor': '#f59e0b', 'icone': 'inter',
        'beneficios': [
            ('30 questões/dia · 7 simulados/dia (até 20 questões)', None),
            ('Banner personalizado', None),
            ('Boost XP e Moedas +15%', None),
            ('100 amigos · 40 grupos', None),
            ('1 Campeonato Grande + 2 Médios/mês', None),
            ('Cor personalizada no nick', None),
            ('Sem anúncios', None),
            ('badge', 'premium_inter'),
        ]
    },
    'advan': {
        'nome': 'Avançado', 'mensal': 39.90, 'anual': 334.90, 'cor': '#a855f7', 'icone': 'advan',
        'beneficios': [
            ('Questões e Simulados ilimitados', None),
            ('GIF como banner', None),
            ('Boost XP e Moedas +30%', None),
            ('Amigos e grupos ilimitados', None),
            ('Competições ilimitadas', None),
            ('Cor em gradiente no nick', None),
            ('Fonte personalizada no nick', None),
            ('Tag personalizada', None),
            ('Sem anúncios', None),
            ('badge', 'premium_advan'),
        ]
    },
}

# Pacotes de moedas
PACOTES_MOEDAS = {
    'starter': {'nome': 'Iniciante', 'moedas': 180, 'bonus': 20, 'preco': 11.90},
    'popular': {'nome': 'Popular', 'moedas': 400, 'bonus': 50, 'preco': 24.90},
    'premium': {'nome': 'Premium', 'moedas': 1500, 'bonus': 300, 'preco': 149.90},
    'ultimate': {'nome': 'Ultimate', 'moedas': 4000, 'bonus': 750, 'preco': 249.90},
}

@main.route('/premium')
@login_required
def premium():
    return render_template('premium/index.html', planos=PLANOS, titulo='Premium')

@main.route('/premium/assinar/<plano>/<ciclo>', methods=['POST'])
@login_required
def premium_assinar(plano, ciclo):
    if plano not in PLANOS or ciclo not in ('mensal','anual'): abort(400)
    preco = PLANOS[plano][ciclo]
    # Register simulated payment record
    from app.models import PagamentoHistorico
    pag = PagamentoHistorico(
        usuario_id=current_user.id,
        plano=plano, ciclo=ciclo, valor=preco, status='pago',
        descricao=f'Assinatura {PLANOS[plano]["nome"]} — {ciclo.capitalize()}'
    )
    db.session.add(pag)
    # Activate premium (simulate gateway approval)
    meses = 1 if ciclo == 'mensal' else 12
    from datetime import timedelta
    current_user.plano_premium = plano
    current_user.premium_expira = datetime.now(timezone.utc) + timedelta(days=30*meses)
    current_user.premium_ciclo = ciclo
    current_user.premium_cancelar_em = None
    db.session.commit()
    flash(f'Plano {PLANOS[plano]["nome"]} ativado! (Integre seu gateway de pagamento para cobranças reais — veja README)', 'success')
    return redirect(url_for('main.premium'))

@main.route('/premium/cancelar', methods=['POST'])
@login_required
def premium_cancelar():
    """Agenda cancelamento ao fim do período atual."""
    if not current_user.premium_ativo:
        flash('Você não possui assinatura ativa.', 'warning')
        return redirect(url_for('main.premium'))
    current_user.premium_cancelar_em = current_user.premium_expira
    from app.models import PagamentoHistorico
    db.session.add(PagamentoHistorico(
        usuario_id=current_user.id,
        plano=current_user.plano_premium or '',
        ciclo=current_user.premium_ciclo or 'mensal',
        valor=0, status='cancelado',
        descricao=f'Cancelamento agendado — expira em {current_user.premium_expira.strftime("%d/%m/%Y") if current_user.premium_expira else "?"}'
    ))
    db.session.commit()
    flash(f'Assinatura cancelada. Você manterá os benefícios até {current_user.premium_expira.strftime("%d/%m/%Y") if current_user.premium_expira else "o fim do período"}.', 'info')
    return redirect(url_for('main.premium'))

@main.route('/premium/reativar', methods=['POST'])
@login_required
def premium_reativar():
    """Cancela o agendamento de cancelamento."""
    current_user.premium_cancelar_em = None
    db.session.commit()
    flash('Cancelamento desfeito. Sua assinatura continuará normalmente.', 'success')
    return redirect(url_for('main.premium'))

@main.route('/premium/trocar/<plano>/<ciclo>', methods=['POST'])
@login_required
def premium_trocar(plano, ciclo):
    """Agenda troca de plano para o próximo ciclo."""
    if plano not in PLANOS or ciclo not in ('mensal','anual'): abort(400)
    if not current_user.premium_ativo:
        return redirect(url_for('main.premium_assinar', plano=plano, ciclo=ciclo), 307)
    # Store pending change — will activate at next billing
    # For now, activate immediately (real gateway handles transitions)
    meses = 1 if ciclo == 'mensal' else 12
    from datetime import timedelta
    preco = PLANOS[plano][ciclo]
    from app.models import PagamentoHistorico
    db.session.add(PagamentoHistorico(
        usuario_id=current_user.id,
        plano=plano, ciclo=ciclo, valor=preco, status='pendente',
        descricao=f'Alteração para {PLANOS[plano]["nome"]} — {ciclo.capitalize()} (ativo no próximo ciclo)'
    ))
    current_user.plano_premium = plano
    current_user.premium_expira = datetime.now(timezone.utc) + timedelta(days=30*meses)
    current_user.premium_ciclo = ciclo
    db.session.commit()
    flash(f'Plano alterado para {PLANOS[plano]["nome"]}! (Ativo imediatamente em modo simulado)', 'success')
    return redirect(url_for('main.premium'))

@main.route('/perfil/pagamentos')
@login_required
def perfil_pagamentos():
    """Histórico privado de pagamentos do usuário."""
    from app.models import PagamentoHistorico
    historico = PagamentoHistorico.query.filter_by(usuario_id=current_user.id)\
        .order_by(PagamentoHistorico.criado_em.desc()).all()
    return render_template('perfil_pagamentos.html', historico=historico, titulo='Meus Pagamentos')

@main.route('/premium/webhook', methods=['POST'])
def premium_webhook():
    data = request.get_json(silent=True) or {}
    gateway_ref = data.get('id')
    plano = data.get('plano')
    usuario_id = data.get('usuario_id')
    ciclo = data.get('ciclo','mensal')
    if not (gateway_ref and plano and usuario_id):
        return jsonify({'erro':'Payload inválido'}),400
    u = Usuario.query.get(usuario_id)
    if not u: return jsonify({'erro':'Usuário não encontrado'}),404
    meses = 1 if ciclo=='mensal' else 12
    expira = datetime.now(timezone.utc)+timedelta(days=30*meses)
    u.plano_premium = plano
    u.premium_expira = expira
    
    db.session.add(Assinatura(
        # pyrefly: ignore [unexpected-keyword]
        usuario_id=u.id,
        # pyrefly: ignore [unexpected-keyword]
        plano=plano,
        # pyrefly: ignore [unexpected-keyword]
        ciclo=ciclo,
        # pyrefly: ignore [unexpected-keyword]
        gateway_ref=gateway_ref,
        # pyrefly: ignore [unexpected-keyword]
        expira=expira
    ))
    db.session.commit()
    return jsonify({'ok':True})

# ════════════════════════════════════════════
#  SOCIAL
# ════════════════════════════════════════════

@main.route('/social')
@login_required
def social():
    # Buscar todas as relações de amizade aceitas
    rels = Amizade.query.filter(
        ((Amizade.solicitante_id == current_user.id) | (Amizade.destinatario_id == current_user.id)),
        Amizade.status == 'aceito'
    ).all()

    amigos_favs = []
    amigos_nao_favs = []
    for rel in rels:
        outro_id = rel.destinatario_id if rel.solicitante_id == current_user.id else rel.solicitante_id
        u = Usuario.query.get(outro_id)
        if not u: continue
        favoritado = rel.favorito_sol if rel.solicitante_id == current_user.id else rel.favorito_dest
        item = {'usuario': u, 'rel': rel, 'favoritado': favoritado}
        if favoritado:
            amigos_favs.append(item)
        else:
            amigos_nao_favs.append(item)

    pendentes = Amizade.query.filter_by(
        destinatario_id=current_user.id, status='pendente').all()

    # Grupos ordenados: favoritos primeiro, depois por última atividade
    membros_grupos = (GrupoMembro.query
                      .filter_by(usuario_id=current_user.id)
                      .join(GrupoChat)
                      .order_by(GrupoMembro.favorito.desc(),
                                GrupoMembro.ultima_atividade.desc()).all())

    grupos = []
    for gm in membros_grupos:
        grupo = gm.grupo
        outro = None
        if grupo.is_direto:
            # Encontrar o outro membro
            outro_membro = GrupoMembro.query.filter(
                GrupoMembro.grupo_id == grupo.id,
                GrupoMembro.usuario_id != current_user.id
            ).first()
            if outro_membro:
                outro = outro_membro.usuario
        grupos.append({'membro': gm, 'grupo': grupo, 'outro_usuario': outro})

    amigos_todos = amigos_favs + amigos_nao_favs
    return render_template('social/index.html',
                           amigos=amigos_todos,
                           amigos_favs=amigos_favs,
                           amigos_nao_favs=amigos_nao_favs,
                           pendentes=pendentes,
                           grupos=grupos, titulo='Social')

@main.route('/social/buscar')
@login_required
def social_buscar():
    q = sanitizar_texto(request.args.get('q',''),60)
    usuarios = []
    if q:
        usuarios = (Usuario.query.filter(
            (Usuario.username.ilike(f'%{q}%'))|(Usuario.nome.ilike(f'%{q}%'))|(Usuario.tag==q))
            .filter(Usuario.id!=current_user.id).limit(20).all())
    return render_template('social/buscar.html', usuarios=usuarios, q=q, titulo='Buscar')

@main.route('/social/adicionar/<int:uid>', methods=['POST'])
@login_required
def social_adicionar(uid):
    if uid==current_user.id: return jsonify({'erro':'Você não pode se adicionar.'}),400
    lim = current_user.limite_amigos
    if lim and len(amigos_ids(current_user.id))>=lim:
        return jsonify({'erro':f'Limite de {lim} amigos atingido.'}),400
    destinatario = Usuario.query.get(uid)
    if destinatario and destinatario.bloquear_pedidos_amizade:
        return jsonify({'ok':False,'erro':'Este usuário não aceita pedidos de amizade.','bloqueado':True}),200
    existente = Amizade.query.filter(
        ((Amizade.solicitante_id==current_user.id)&(Amizade.destinatario_id==uid))|
        ((Amizade.solicitante_id==uid)&(Amizade.destinatario_id==current_user.id))).first()
    if existente: return jsonify({'erro':'Solicitação já existe.'}),400
    # pyrefly: ignore [unexpected-keyword]
    db.session.add(Amizade(solicitante_id=current_user.id,destinatario_id=uid))
    db.session.commit()
    return jsonify({'ok':True,'msg':'Solicitação enviada!'})

@main.route('/social/aceitar/<int:aid>', methods=['POST'])
@login_required
def social_aceitar(aid):
    rel = Amizade.query.get_or_404(aid)
    if rel.destinatario_id!=current_user.id: abort(403)
    rel.status='aceito'; db.session.commit()
    return jsonify({'ok':True})

@main.route('/social/recusar/<int:aid>', methods=['POST'])
@login_required
def social_recusar(aid):
    rel = Amizade.query.get_or_404(aid)
    if rel.destinatario_id!=current_user.id: abort(403)
    rel.status='recusado'; db.session.commit()
    return jsonify({'ok':True})

@main.route('/social/remover/<int:uid>', methods=['POST'])
@login_required
def social_remover(uid):
    rel = Amizade.query.filter(
        ((Amizade.solicitante_id==current_user.id)&(Amizade.destinatario_id==uid))|
        ((Amizade.solicitante_id==uid)&(Amizade.destinatario_id==current_user.id)),
        Amizade.status=='aceito').first_or_404()
    db.session.delete(rel); db.session.commit()
    return jsonify({'ok':True})

@main.route('/social/grupo/novo', methods=['GET','POST'])
@login_required
def grupo_novo():
    from app.forms import FormGrupo
    form = FormGrupo()
    lim = current_user.limite_grupos
    qtd = GrupoMembro.query.filter_by(usuario_id=current_user.id).count()
    if lim and qtd >= lim:
        flash(f'Limite de {lim} grupos atingido.','warning')
        return redirect(url_for('main.social'))
    # Amigos para seleção inicial
    ids_am = amigos_ids(current_user.id)
    amigos_lista = [Usuario.query.get(aid) for aid in ids_am]
    amigos_lista = [u for u in amigos_lista if u]
    if form.validate_on_submit():
        nome  = sanitizar_texto(form.nome.data,100)
        # pyrefly: ignore [unexpected-keyword]
        grupo = GrupoChat(nome=nome,icone=form.icone.data or '\U0001F4AC',criador_id=current_user.id)
        db.session.add(grupo); db.session.flush()
        # pyrefly: ignore [unexpected-keyword]
        db.session.add(GrupoMembro(grupo_id=grupo.id,usuario_id=current_user.id,eh_admin=True))
        # Adicionar amigos selecionados
        membros_sel = request.form.getlist('membros_iniciais')
        ids_am_set = set(ids_am)
        for mid_str in membros_sel:
            try:
                mid = int(mid_str)
            except ValueError:
                continue
            if mid != current_user.id and mid in ids_am_set:
                # pyrefly: ignore [unexpected-keyword]
                db.session.add(GrupoMembro(grupo_id=grupo.id,usuario_id=mid))
        db.session.commit()
        flash('Grupo criado!','success')
        return redirect(url_for('main.grupo_chat',grupo_id=grupo.id))
    return render_template('social/grupo_novo.html', form=form, amigos_lista=amigos_lista, titulo='Novo Grupo')

@main.route('/social/grupo/<int:grupo_id>')
@login_required
def grupo_chat(grupo_id):
    from app.forms import FormMensagem
    import re as _re
    grupo  = GrupoChat.query.get_or_404(grupo_id)
    membro = GrupoMembro.query.filter_by(grupo_id=grupo_id, usuario_id=current_user.id).first()
    if not membro: abort(403)

    # Redirect to slug URL
    if grupo.is_direto:
        outro_m2 = GrupoMembro.query.filter(
            GrupoMembro.grupo_id == grupo_id,
            GrupoMembro.usuario_id != current_user.id).first()
        slug = outro_m2.usuario.username if outro_m2 else str(grupo_id)
    else:
        slug = _re.sub(r'[^a-z0-9\-]', '-', grupo.nome.lower().strip())
        slug = _re.sub(r'-+', '-', slug).strip('-') or str(grupo_id)
    # Only redirect if URL doesn't already have slug (avoid loop)
    from flask import request as _req
    if not _req.path.endswith('/' + slug):
        return redirect(url_for('main.grupo_chat_slug', slug=slug, grupo_id=grupo_id), 302)

    # Atualizar ultima_atividade do membro
    membro.ultima_atividade = datetime.now(timezone.utc)

    msgs = (Mensagem.query.filter_by(grupo_id=grupo_id, deletado=False)
               .order_by(Mensagem.enviado_em.asc()).limit(100).all())
    membros = GrupoMembro.query.filter_by(grupo_id=grupo_id).all()
    form = FormMensagem()

    # Outro usuário para DM
    outro_usuario = None
    if grupo.is_direto:
        outro_m = GrupoMembro.query.filter(
            GrupoMembro.grupo_id == grupo_id,
            GrupoMembro.usuario_id != current_user.id).first()
        if outro_m:
            outro_usuario = outro_m.usuario

    # Admin check
    membro_admin = membro.eh_admin or grupo.criador_id == current_user.id

    # Amigos para adicionar ao grupo
    ids_amigos = amigos_ids(current_user.id)
    ids_no_grupo = {m.usuario_id for m in membros}
    amigos_ids_para_grupo = [Usuario.query.get(aid) for aid in ids_amigos
                              if aid not in ids_no_grupo]
    amigos_ids_para_grupo = [u for u in amigos_ids_para_grupo if u]

    db.session.commit()
    titulo = outro_usuario.nome_completo if outro_usuario else grupo.nome
    return render_template('social/chat.html', grupo=grupo, msgs=msgs,
                           membros=membros, form=form,
                           outro_usuario=outro_usuario,
                           membro_admin=membro_admin,
                           amigos_ids_para_grupo=amigos_ids_para_grupo,
                           titulo=titulo)

@main.route('/social/grupo/<int:grupo_id>/<slug>')
@login_required
def grupo_chat_slug(grupo_id, slug):
    """Slug-based URL — just delegates to grupo_chat logic."""
    from app.forms import FormMensagem
    grupo = GrupoChat.query.get_or_404(grupo_id)
    membro = GrupoMembro.query.filter_by(grupo_id=grupo_id, usuario_id=current_user.id).first()
    if not membro: abort(403)
    membro.ultima_atividade = datetime.now(timezone.utc)
    msgs = (Mensagem.query.filter_by(grupo_id=grupo_id, deletado=False)
               .order_by(Mensagem.enviado_em.asc()).limit(100).all())
    membros = GrupoMembro.query.filter_by(grupo_id=grupo_id).all()
    form = FormMensagem()
    outro_usuario = None
    if grupo.is_direto:
        outro_m = GrupoMembro.query.filter(
            GrupoMembro.grupo_id == grupo_id,
            GrupoMembro.usuario_id != current_user.id).first()
        if outro_m: outro_usuario = outro_m.usuario
    membro_admin = membro.eh_admin or grupo.criador_id == current_user.id
    ids_amigos = amigos_ids(current_user.id)
    ids_no_grupo = {m.usuario_id for m in membros}
    amigos_ids_para_grupo = [u for u in [Usuario.query.get(aid) for aid in ids_amigos if aid not in ids_no_grupo] if u]
    db.session.commit()
    titulo = outro_usuario.nome_completo if outro_usuario else grupo.nome
    return render_template('social/chat.html', grupo=grupo, msgs=msgs,
                           membros=membros, form=form,
                           outro_usuario=outro_usuario,
                           membro_admin=membro_admin,
                           amigos_ids_para_grupo=amigos_ids_para_grupo,
                           titulo=titulo)

@main.route('/social/grupo/<int:grupo_id>/enviar', methods=['POST'])
@login_required
def grupo_enviar(grupo_id):
    from app.forms import FormMensagem
    import os
    grupo = GrupoChat.query.get_or_404(grupo_id)
    membro = GrupoMembro.query.filter_by(grupo_id=grupo_id, usuario_id=current_user.id).first()
    if not membro: abort(403)
    form = FormMensagem()
    if form.validate_on_submit():
        conteudo = sanitizar_texto(form.conteudo.data or '', 2000)
        arquivo_path = None
        tipo_msg = 'texto'

        # Processar arquivo (imagem, gif, pdf, doc, zip, etc.)
        if form.imagem.data and form.imagem.data.filename:
            arquivo = form.imagem.data
            nome_orig = arquivo.filename
            permitido, motivo_arq = moderar_arquivo(arquivo, nome_orig)
            if not permitido:
                flash(f'Arquivo bloqueado: {motivo_arq}', 'danger')
                return redirect(url_for('main.grupo_chat', grupo_id=grupo_id))
            arquivo.seek(0)
            ext = os.path.splitext(nome_orig)[1].lower()
            nome_salvo = nome_arquivo_seguro(nome_orig, 'cf_')
            pasta = os.path.join(current_app.root_path, 'static', 'data', 'chat_files')
            os.makedirs(pasta, exist_ok=True)
            arquivo.save(os.path.join(pasta, nome_salvo))
            arquivo_path = nome_salvo
            tipo_msg = 'imagem' if ext in ('.png','.jpg','.jpeg','.webp','.gif') else 'arquivo'

        if not conteudo and not arquivo_path:
            flash('Mensagem vazia.', 'warning')
            return redirect(url_for('main.grupo_chat', grupo_id=grupo_id))

        # Moderação de texto
        if conteudo:
            ok, motivo = validar_texto_seguro(conteudo)
            if not ok:
                db.session.add(ConteudoBloqueado(
                    # pyrefly: ignore [unexpected-keyword]
                    usuario_id=current_user.id,
                    # pyrefly: ignore [unexpected-keyword]
                    tipo='mensagem',
                    # pyrefly: ignore [unexpected-keyword]
                    referencia=conteudo[:100],
                    # pyrefly: ignore [unexpected-keyword]
                    motivo=motivo))
                db.session.commit()
                flash('Mensagem bloqueada por conteúdo indevido.', 'danger')
                return redirect(url_for('main.grupo_chat', grupo_id=grupo_id))

            # Censura de palavrões se configurado
            if current_user.censurar_conteudo:
                import re
                PALAVROES = ['palavrão1', 'palavrão2', 'merda', 'porra', 'caralho',
                             'foda', 'puta', 'viado', 'buceta']
                for p in PALAVROES:
                    conteudo = re.sub(p, '****', conteudo, flags=re.IGNORECASE)

        db.session.add(Mensagem(
            # pyrefly: ignore [unexpected-keyword]
            grupo_id=grupo_id,
            # pyrefly: ignore [unexpected-keyword]
            remetente_id=current_user.id,
            # pyrefly: ignore [unexpected-keyword]
            conteudo=conteudo,
            # pyrefly: ignore [unexpected-keyword]
            imagem_path=arquivo_path,
            # pyrefly: ignore [unexpected-keyword]
            tipo=tipo_msg))
        # Atualizar ultima_atividade do membro
        membro.ultima_atividade = datetime.now(timezone.utc)
        db.session.commit()
    return redirect(url_for('main.grupo_chat', grupo_id=grupo_id))

@main.route('/social/dm/<int:uid>')
@login_required
def dm_chat(uid):
    outro = Usuario.query.get_or_404(uid)
    amizade = Amizade.query.filter(
        ((Amizade.solicitante_id==current_user.id)&(Amizade.destinatario_id==uid))|
        ((Amizade.solicitante_id==uid)&(Amizade.destinatario_id==current_user.id)),
        Amizade.status=='aceito').first()
    if not amizade:
        flash('Precisa ser amigo para enviar mensagens.','warning')
        return redirect(url_for('main.perfil',username=outro.username))
    ids_meu = {m.grupo_id for m in GrupoMembro.query.filter_by(usuario_id=current_user.id).all()}
    ids_outr = {m.grupo_id for m in GrupoMembro.query.filter_by(usuario_id=uid).all()}
    comuns = ids_meu & ids_outr
    grupo_dm = GrupoChat.query.filter(GrupoChat.id.in_(comuns),GrupoChat.is_direto==True).first() if comuns else None
    if not grupo_dm:
        # pyrefly: ignore [unexpected-keyword]
        grupo_dm = GrupoChat(nome=f'dm',criador_id=current_user.id,is_direto=True)
        db.session.add(grupo_dm); db.session.flush()
        # pyrefly: ignore [unexpected-keyword]
        db.session.add(GrupoMembro(grupo_id=grupo_dm.id,usuario_id=current_user.id,eh_admin=True))
        # pyrefly: ignore [unexpected-keyword]
        db.session.add(GrupoMembro(grupo_id=grupo_dm.id,usuario_id=uid))
        db.session.commit()
    return redirect(url_for('main.grupo_chat',grupo_id=grupo_dm.id))

# ════════════════════════════════════════════
#  ADMIN
# ════════════════════════════════════════════

@main.route('/admin')
@login_required
@admin_required
def admin_painel():
    return render_template('admin/painel.html',
                           total_usuarios=Usuario.query.count(),
                           total_materias=Materia.query.count(),
                           total_questoes=Questao.query.count(),
                           total_respostas=RespostaUsuario.query.count(),titulo='Admin')

@main.route('/admin/materias')
@login_required
@admin_required
def admin_materias():
    return render_template('admin/materias.html',
                           materias=Materia.query.order_by(Materia.nome).all(),titulo='Matérias')

@main.route('/admin/materias/nova', methods=['GET','POST'])
@login_required
@admin_required
def admin_nova_materia():
    form = FormMateria()
    if form.validate_on_submit():
        # pyrefly: ignore [unexpected-keyword]
        db.session.add(Materia(nome=sanitizar_texto(form.nome.data,100),
        # pyrefly: ignore [unexpected-keyword]
                               icone=form.icone.data or '\U0001F4DA',cor=form.cor.data or '#6366f1'))
        db.session.commit(); flash('Matéria criada!','success')
        return redirect(url_for('main.admin_materias'))
    return render_template('admin/form_materia.html',form=form,titulo='Nova Matéria',acao='Criar')

@main.route('/admin/materias/<int:id>/editar', methods=['GET','POST'])
@login_required
@admin_required
def admin_editar_materia(id):
    m = Materia.query.get_or_404(id); form = FormMateria(obj=m)
    if form.validate_on_submit():
        m.nome=sanitizar_texto(form.nome.data,100); m.icone=form.icone.data or '\U0001F4DA'
        m.cor=form.cor.data or '#6366f1'; db.session.commit(); flash('Atualizada!','success')
        return redirect(url_for('main.admin_materias'))
    return render_template('admin/form_materia.html',form=form,titulo='Editar Matéria',acao='Salvar')

@main.route('/admin/materias/<int:id>/excluir', methods=['POST'])
@login_required
@admin_required
def admin_excluir_materia(id):
    m = Materia.query.get_or_404(id); db.session.delete(m); db.session.commit()
    flash(f'"{m.nome}" excluída.','info'); return redirect(url_for('main.admin_materias'))

@main.route('/admin/questoes')
@login_required
@admin_required
def admin_questoes():
    mid = request.args.get('materia_id',type=int)
    q   = Questao.query
    if mid: q=q.filter_by(materia_id=mid)
    return render_template('admin/questoes.html',
                           questoes=q.order_by(Questao.criado_em.desc()).all(),
                           materias=Materia.query.order_by(Materia.nome).all(),
                           materia_id_filtro=mid,titulo='Questões')

@main.route('/admin/questoes/nova', methods=['GET','POST'])
@login_required
@admin_required
def admin_nova_questao():
    form = FormQuestao()
    form.materia_id.choices = [(m.id,m.nome) for m in Materia.query.order_by(Materia.nome).all()]
    if form.validate_on_submit():
        img = salvar_upload(form.imagem.data,'img_questao','q_') if form.imagem.data else None
        q = Questao(
            # pyrefly: ignore [unexpected-keyword]
            enunciado=sanitizar_texto(form.enunciado.data,2000),
            # pyrefly: ignore [unexpected-keyword]
            explicacao=sanitizar_texto(form.explicacao.data or '',1000) or None,
            # pyrefly: ignore [unexpected-keyword]
            dificuldade=form.dificuldade.data, materia_id=form.materia_id.data,
            # pyrefly: ignore [unexpected-keyword]
            conteudo=sanitizar_texto(form.conteudo.data or '',100) or None,
            # pyrefly: ignore [unexpected-keyword]
            imagem_path=img, tipo=form.tipo_questao.data,
            # pyrefly: ignore [unexpected-keyword]
            resposta_correta=sanitizar_texto(form.resposta_correta.data or '',2000) or None)
        db.session.add(q); db.session.flush()
        if form.tipo_questao.data == 'multipla':
            letra_correta = form.correta.data
            for letra, texto in [('a',form.alternativa_a.data),('b',form.alternativa_b.data),
                                  ('c',form.alternativa_c.data),('d',form.alternativa_d.data)]:
                if texto:
                    # pyrefly: ignore [unexpected-keyword]
                    db.session.add(Alternativa(texto=sanitizar_texto(texto,500),
                    # pyrefly: ignore [unexpected-keyword]
                                               correta=(letra==letra_correta),questao_id=q.id))
        db.session.commit(); flash('Questão criada!','success')
        return redirect(url_for('main.admin_questoes'))
    return render_template('admin/form_questao.html',form=form,titulo='Nova Questão',acao='Criar')

@main.route('/admin/questoes/<int:id>/editar', methods=['GET','POST'])
@login_required
@admin_required
def admin_editar_questao(id):
    questao = Questao.query.get_or_404(id); form = FormQuestao()
    form.materia_id.choices = [(m.id,m.nome) for m in Materia.query.order_by(Materia.nome).all()]
    if form.validate_on_submit():
        if form.imagem.data and form.imagem.data.filename:
            img = salvar_upload(form.imagem.data,'img_questao','q_')
            if img: questao.imagem_path=img
        questao.enunciado = sanitizar_texto(form.enunciado.data,2000)
        questao.explicacao = sanitizar_texto(form.explicacao.data or '',1000) or None
        questao.dificuldade = form.dificuldade.data
        questao.materia_id = form.materia_id.data
        questao.conteudo = sanitizar_texto(form.conteudo.data or '',100) or None
        questao.tipo = form.tipo_questao.data
        questao.resposta_correta = sanitizar_texto(form.resposta_correta.data or '',2000) or None
        if form.tipo_questao.data == 'multipla':
            Alternativa.query.filter_by(questao_id=questao.id).delete()
            letra_correta = form.correta.data
            for letra,texto in [('a',form.alternativa_a.data),('b',form.alternativa_b.data),
                                 ('c',form.alternativa_c.data),('d',form.alternativa_d.data)]:
                if texto:
                    # pyrefly: ignore [unexpected-keyword]
                    db.session.add(Alternativa(texto=sanitizar_texto(texto,500),
                    # pyrefly: ignore [unexpected-keyword]
                                               correta=(letra==letra_correta),questao_id=questao.id))
        db.session.commit(); flash('Atualizada!','success')
        return redirect(url_for('main.admin_questoes'))
    elif request.method == 'GET':
        form.enunciado.data = questao.enunciado; form.explicacao.data = questao.explicacao
        form.dificuldade.data = questao.dificuldade; form.materia_id.data = questao.materia_id
        form.conteudo.data = questao.conteudo; form.tipo_questao.data = questao.tipo
        form.resposta_correta.data = questao.resposta_correta
        alts=questao.alternativas; letras = ['a','b','c','d']
        campos = [form.alternativa_a,form.alternativa_b,form.alternativa_c,form.alternativa_d]
        for i, alt in enumerate(alts[:4]):
            campos[i].data = alt.texto
            if alt.correta: form.correta.data = letras[i]
    return render_template('admin/form_questao.html',form=form,titulo='Editar Questão',
                           acao='Salvar',questao=questao)

@main.route('/admin/questoes/<int:id>/excluir', methods=['POST'])
@login_required
@admin_required
def admin_excluir_questao(id):
    q = Questao.query.get_or_404(id); db.session.delete(q); db.session.commit()
    flash('Excluída.','info'); return redirect(url_for('main.admin_questoes'))

@main.route('/admin/usuarios')
@login_required
@admin_required
def admin_usuarios():
    return render_template('admin/usuarios.html',
                           usuarios=Usuario.query.order_by(Usuario.criado_em.desc()).all(),
                           titulo='Usuários')

@main.route('/admin/usuarios/<int:uid>/banir', methods=['POST'])
@login_required
@admin_required
def admin_banir(uid):
    u = Usuario.query.get_or_404(uid); u.is_banido=not u.is_banido; db.session.commit()
    flash(f'{u.username} {"banido" if u.is_banido else "desbanido"}.','info')
    return redirect(url_for('main.admin_usuarios'))

@main.route('/admin/logs')
@login_required
@admin_required
def admin_logs():
    logs = LogAuditoria.query.order_by(LogAuditoria.criado_em.desc()).limit(200).all()
    return render_template('admin/logs.html',logs=logs,titulo='Logs')

# ════════════════════════════════════════════
#  ERROS
# ════════════════════════════════════════════

@main.app_errorhandler(403)
def erro_403(e): return render_template('errors/403.html'),403
@main.app_errorhandler(404)
def erro_404(e): return render_template('errors/404.html'),404
@main.app_errorhandler(500)
def erro_500(e): db.session.rollback(); return render_template('errors/500.html'),500

# ════════════════════════════════════════════
#  ADS — SISTEMA DE ANÚNCIOS
# ════════════════════════════════════════════

@main.route('/api/ads/assistir', methods=['POST'])
@login_required
def ads_assistir():
    """Usuário assistiu anúncio — ganha 2 questões extras."""
    from app.models import AdsCredit
    if not current_user.tem_ads:
        return jsonify({'erro': 'Você não precisa de créditos.'}), 400

    # Limitar: máx 3 créditos por dia
    from datetime import date
    hoje_inicio = datetime(date.today().year, date.today().month, date.today().day, tzinfo=timezone.utc)
    creditos_hoje = AdsCredit.query.filter(
        AdsCredit.usuario_id == current_user.id,
        AdsCredit.criado_em >= hoje_inicio
    ).count()
    if creditos_hoje >= 3:
        return jsonify({'erro': 'Máximo de 3 créditos de anúncio por dia atingido.', 'max': True}), 429

    # pyrefly: ignore [unexpected-keyword]
    cred = AdsCredit(usuario_id=current_user.id, questoes_extras=2)
    db.session.add(cred)
    db.session.commit()
    # Adicionar ao limite diário temporariamente
    current_user.questoes_hoje = max(0, current_user.questoes_hoje - 2)
    db.session.commit()
    return jsonify({'ok': True, 'questoes_extras': 2,
                    'questoes_restantes': max(0, current_user.limite_questoes_dia - current_user.questoes_hoje) if current_user.limite_questoes_dia else 999})


@main.route('/api/ads/status')
@login_required
def ads_status():
    from app.models import AdsCredit
    from datetime import date
    hoje_inicio = datetime(date.today().year, date.today().month, date.today().day, tzinfo=timezone.utc)
    creditos_hoje = AdsCredit.query.filter(
        AdsCredit.usuario_id == current_user.id,
        AdsCredit.criado_em >= hoje_inicio
    ).count()
    lim = current_user.limite_questoes_dia
    restantes = max(0, lim - current_user.questoes_hoje) if lim else 999
    return jsonify({
        'tem_ads': current_user.tem_ads,
        'creditos_hoje': creditos_hoje,
        'max_creditos_dia': 3,
        'questoes_restantes': restantes,
        'pode_assistir': creditos_hoje < 3 and current_user.tem_ads
    })


# ════════════════════════════════════════════
#  TORNEIOS / COMPETIÇÕES
# ════════════════════════════════════════════

@main.route('/competicoes')
@login_required
def competicoes():
    from app.models import Torneio, TorneioParticipante
    agora = datetime.now(timezone.utc)
    abertos = Torneio.query.filter(Torneio.status == 'aberto',
                                     Torneio.fim > agora).order_by(Torneio.inicio).all()
    ativos = Torneio.query.filter(Torneio.status == 'em_andamento').order_by(Torneio.inicio).all()
    finalizados = Torneio.query.filter(Torneio.status == 'finalizado')\
                    .order_by(Torneio.fim.desc()).limit(10).all()

    # Participações do usuário
    minhas_ids = {p.torneio_id for p in TorneioParticipante.query.filter_by(
        usuario_id=current_user.id).all()}

    materias = Materia.query.order_by(Materia.nome).all()
    return render_template('competicoes/index.html',
                           abertos=abertos, ativos=ativos, finalizados=finalizados,
                           minhas_ids=minhas_ids, materias=materias, titulo='Competições')


@main.route('/competicoes/<int:torneio_id>/entrar', methods=['POST'])
@login_required
def competicao_entrar(torneio_id):
    from app.models import Torneio, TorneioParticipante
    torneio = Torneio.query.get_or_404(torneio_id)

    if torneio.status not in ('aberto', 'em_andamento'):
        return jsonify({'erro': 'Torneio não está aberto.'}), 400
    if not current_user.pode_competicoes:
        return jsonify({'erro': 'Competições disponíveis a partir do Plano Intermediário.'}), 403

    # Limite de torneios do mês para inter
    if current_user.plano_efetivo == 'inter':
        from datetime import date
        hoje = date.today()
        if current_user.ultimo_reset_torneios.month != hoje.month:
            current_user.torneios_este_mes = 0
            current_user.ultimo_reset_torneios = hoje
        if current_user.torneios_este_mes >= 3:
            return jsonify({'erro': 'Limite de 3 torneios/mês para o plano Intermediário.'}), 429

    existente = TorneioParticipante.query.filter_by(
        torneio_id=torneio_id, usuario_id=current_user.id).first()
    if existente:
        return jsonify({'erro': 'Você já está participando.'}), 400

    # pyrefly: ignore [unexpected-keyword]
    part = TorneioParticipante(torneio_id=torneio_id, usuario_id=current_user.id)
    db.session.add(part)
    if current_user.plano_efetivo == 'inter':
        current_user.torneios_este_mes += 1
    db.session.commit()
    return jsonify({'ok': True})


@main.route('/competicoes/<int:torneio_id>')
@login_required
def competicao_detalhe(torneio_id):
    from app.models import Torneio, TorneioParticipante, TorneioResposta
    torneio = Torneio.query.get_or_404(torneio_id)
    minha_part = TorneioParticipante.query.filter_by(
        torneio_id=torneio_id, usuario_id=current_user.id).first()

    # Ranking do torneio
    ranking_part = TorneioParticipante.query\
        .filter_by(torneio_id=torneio_id)\
        .order_by(TorneioParticipante.pontuacao.desc()).limit(20).all()

    # Questões do torneio (aleatórias fixas por seed do torneio_id)
    questoes = []
    if torneio.materia_id:
        q_query = Questao.query.filter_by(materia_id=torneio.materia_id,
                                          dificuldade=torneio.dificuldade)
    else:
        q_query = Questao.query.filter_by(dificuldade=torneio.dificuldade)
    questoes = q_query.order_by(db.func.random()).limit(torneio.num_questoes).all()

    # IDs já respondidos
    respondidas_ids = set()
    if minha_part:
        respondidas_ids = {r.questao_id for r in TorneioResposta.query.filter_by(
            participante_id=minha_part.id).all()}

    return render_template('competicoes/detalhe.html', torneio=torneio,
                           minha_part=minha_part, ranking_part=ranking_part,
                           questoes=questoes, respondidas_ids=respondidas_ids,
                           titulo=torneio.nome)


@main.route('/api/competicoes/responder', methods=['POST'])
@login_required
def competicao_responder():
    from app.models import Torneio, TorneioParticipante, TorneioResposta
    data = request.get_json()
    if not data: return jsonify({'erro': 'Inválido.'}), 400

    torneio_id = data.get('torneio_id')
    questao_id = data.get('questao_id')
    alternativa_id = data.get('alternativa_id')

    torneio = Torneio.query.get(torneio_id)
    if not torneio or torneio.status not in ('aberto', 'em_andamento'):
        return jsonify({'erro': 'Torneio inativo.'}), 400

    minha_part = TorneioParticipante.query.filter_by(
        torneio_id=torneio_id, usuario_id=current_user.id).first()
    if not minha_part:
        return jsonify({'erro': 'Você não está participando.'}), 403

    # Verificar se já respondeu
    ja = TorneioResposta.query.filter_by(
        participante_id=minha_part.id, questao_id=questao_id).first()
    if ja:
        return jsonify({'erro': 'Já respondida.'}), 400

    questao = Questao.query.get(questao_id)
    alternativa = Alternativa.query.get(alternativa_id)
    if not questao or not alternativa:
        return jsonify({'erro': 'Questão inválida.'}), 404

    acertou = alternativa.correta
    pontos = {'facil': 10, 'medio': 25, 'dificil': 50}.get(questao.dificuldade, 10)

    db.session.add(TorneioResposta( 
        # pyrefly: ignore [unexpected-keyword]
        torneio_id=torneio_id, participante_id=minha_part.id,
        # pyrefly: ignore [unexpected-keyword]
        questao_id=questao_id, alternativa_id=alternativa_id, acertou=acertou))

    minha_part.respondidas += 1
    if acertou:
        minha_part.acertos   += 1
        minha_part.pontuacao += pontos

    # Verificar se finalizou todas
    if minha_part.respondidas >= torneio.num_questoes:
        minha_part.finalizado = True

    db.session.commit()
    correta = questao.alternativa_correta
    return jsonify({
        'acertou': acertou,
        'pontos': pontos if acertou else 0,
        'pontuacao_total': minha_part.pontuacao,
        'alternativa_correta_id': correta.id if correta else None,
        'explicacao': questao.explicacao or '',
        'finalizado': minha_part.finalizado,
    })


@main.route('/competicoes/<int:torneio_id>/finalizar', methods=['POST'])
@login_required
def competicao_finalizar(torneio_id):
    """Admin finaliza o torneio e distribui recompensas."""
    from app.models import Torneio, TorneioParticipante
    torneio = Torneio.query.get_or_404(torneio_id)
    if not current_user.is_admin: abort(403)

    # Ordenar por pontuação e distribuir
    participantes = TorneioParticipante.query.filter_by(torneio_id=torneio_id)\
        .order_by(TorneioParticipante.pontuacao.desc()).all()

    recompensas = [
        (torneio.recompensa_xp_1, torneio.recompensa_moedas_1),
        (torneio.recompensa_xp_2, torneio.recompensa_moedas_2),
        (torneio.recompensa_xp_3, torneio.recompensa_moedas_3),
    ]
    for i, part in enumerate(participantes):
        part.posicao = i + 1
        if not part.recompensa_paga and i < 3:
            xp_r, m_r = recompensas[i]
            part.usuario.xp     += xp_r
            part.usuario.moedas += m_r
            part.recompensa_paga = True
            # Badge temporária para top 3
            if torneio.badge_temp:
                part.usuario.badge_ativa = torneio.badge_temp

    torneio.status = 'finalizado'
    db.session.commit()
    flash('Torneio finalizado e recompensas distribuídas!', 'success')
    return redirect(url_for('main.competicao_detalhe', torneio_id=torneio_id))


@main.route('/admin/competicoes/novo', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_novo_torneio():
    from app.models import Torneio
    from app.forms import FormTorneio
    from datetime import datetime as _dt
    form = FormTorneio()
    form.materia_id.choices = [(0, 'Todas')] + [
        (m.id, m.nome) for m in Materia.query.order_by(Materia.nome).all()]
    if form.validate_on_submit():
        torneio = Torneio(
            # pyrefly: ignore [unexpected-keyword]
            nome=sanitizar_texto(form.nome.data, 100),  
            # pyrefly: ignore [unexpected-keyword]
            descricao=sanitizar_texto(form.descricao.data or '', 500),
            # pyrefly: ignore [unexpected-keyword]
            tipo=form.tipo.data,
            # pyrefly: ignore [unexpected-keyword]
            materia_id=form.materia_id.data if form.materia_id.data else None,
            # pyrefly: ignore [unexpected-keyword]
            dificuldade=form.dificuldade.data,
            # pyrefly: ignore [unexpected-keyword]
            num_questoes=form.num_questoes.data,
            # pyrefly: ignore [unexpected-keyword]
            inicio=_dt.strptime(form.inicio.data, '%d/%m/%Y %H:%M'),
            # pyrefly: ignore [unexpected-keyword]
            fim=_dt.strptime(form.fim.data, '%d/%m/%Y %H:%M'),
            # pyrefly: ignore [unexpected-keyword]
            recompensa_xp_1=form.recompensa_xp_1.data,
            # pyrefly: ignore [unexpected-keyword]
            recompensa_xp_2=form.recompensa_xp_2.data,
            # pyrefly: ignore [unexpected-keyword]
            recompensa_xp_3=form.recompensa_xp_3.data,
            # pyrefly: ignore [unexpected-keyword]
            recompensa_moedas_1=form.recompensa_moedas_1.data,
            # pyrefly: ignore [unexpected-keyword]
            recompensa_moedas_2=form.recompensa_moedas_2.data,
            # pyrefly: ignore [unexpected-keyword]
            recompensa_moedas_3=form.recompensa_moedas_3.data,
            # pyrefly: ignore [unexpected-keyword]
            badge_temp=form.badge_temp.data or None,
        )
        db.session.add(torneio)
        db.session.commit()
        flash('Torneio criado!', 'success')
        return redirect(url_for('main.competicoes'))
    return render_template('admin/form_torneio.html', form=form, titulo='Novo Torneio')


# ════════════════════════════════════════════
#  PACOTES DE MOEDAS
# ════════════════════════════════════════════

@main.route('/loja/moedas')
@login_required
def loja_moedas():
    from app.models import CompraMoedas
    ja_comprou = CompraMoedas.query.filter_by(
        usuario_id=current_user.id, status='pago').count() > 0
    return render_template('loja/moedas.html',
                           pacotes=PACOTES_MOEDAS,
                           ja_comprou=ja_comprou, titulo='Comprar Moedas')


@main.route('/loja/moedas/comprar/<pacote_id>', methods=['POST'])
@login_required
def loja_moedas_comprar(pacote_id):
    from app.models import CompraMoedas
    if pacote_id not in PACOTES_MOEDAS:
        abort(400)
    pacote = PACOTES_MOEDAS[pacote_id]
    ja_comprou = CompraMoedas.query.filter_by(
        usuario_id=current_user.id, status='pago').count() > 0
    eh_primeira = not ja_comprou

    # Criar registro pendente
    compra = CompraMoedas(
        # pyrefly: ignore [unexpected-keyword]
        usuario_id=current_user.id,
        # pyrefly: ignore [unexpected-keyword]
        pacote_id=pacote_id,    
        # pyrefly: ignore [unexpected-keyword]
        moedas_base=pacote['moedas'],
        # pyrefly: ignore [unexpected-keyword]
        moedas_bonus=pacote['bonus'] if eh_primeira else 0,
        # pyrefly: ignore [unexpected-keyword]
        valor_brl=pacote['preco'],
        # pyrefly: ignore [unexpected-keyword]
        eh_primeira=eh_primeira,
    )
    db.session.add(compra)
    db.session.commit()

    # TODO: integrar gateway (MP / Stripe) — redirecionar para checkout
    flash(f'Redirecione para o gateway de pagamento. Compra #{compra.id} criada. '
          f'Veja README para integração completa.', 'info')
    return redirect(url_for('main.loja_moedas'))


@main.route('/loja/moedas/webhook', methods=['POST'])
def loja_moedas_webhook():
    """Confirmar pagamento do gateway e creditar moedas."""
    from app.models import CompraMoedas
    data = request.get_json(silent=True) or {}
    compra_id = data.get('compra_id')
    if not compra_id:
        return jsonify({'erro': 'Payload inválido'}), 400
    compra = CompraMoedas.query.get(compra_id)
    if not compra or compra.status == 'pago':
        return jsonify({'ok': True})
    compra.status = 'pago'
    compra.gateway_ref = data.get('gateway_ref', '')
    total = compra.moedas_base + compra.moedas_bonus
    compra.usuario.moedas += total
    db.session.commit()
    return jsonify({'ok': True, 'moedas_creditadas': total})


# ════════════════════════════════════════════
#  EDITAR PERFIL — CENSURAR CONTEÚDO
# ════════════════════════════════════════════

@main.route('/api/perfil/censurar', methods=['POST'])
@login_required
def toggle_censura():
    data = request.get_json()
    current_user.censurar_conteudo = bool(data.get('valor', False))
    db.session.commit()
    return jsonify({'ok': True, 'censurar': current_user.censurar_conteudo})


# ════════════════════════════════════════════
#  SISTEMA TRIAL (1 mês grátis)
# ════════════════════════════════════════════

@main.route('/api/trial/aceitar', methods=['POST'])
@login_required
def trial_aceitar():
    from app.models import OfertaTrial
    oferta = OfertaTrial.query.filter_by(
        usuario_id=current_user.id, aceito=False).first()
    if not oferta:
        return jsonify({'erro': 'Nenhuma oferta ativa.'}), 404
    oferta.aceito = True
    oferta.aceito_em = datetime.now(timezone.utc)
    # Conceder 1 mês grátis de Premium Básico
    current_user.plano_premium = 'basic'
    current_user.premium_expira = datetime.now(timezone.utc) + timedelta(days=30)
    db.session.commit()
    return jsonify({'ok': True, 'msg': '\U0001F389 1 mês de Premium Básico ativado!'})


def verificar_oferta_trial(usuario):
    """Chamar no dashboard — verifica se usuário merece oferta trial."""
    from app.models import OfertaTrial
    if usuario.premium_ativo or usuario.trial_ofertado:
        return False
    # Usuário com conta há >= 30 dias sem premium
    from datetime import timezone as tz
    tempo = datetime.now(timezone.utc) - usuario.criado_em.replace(tzinfo=timezone.utc)
    if tempo.days < 30:
        return False
    # Verificar se já não recebeu oferta
    ja_teve = OfertaTrial.query.filter_by(usuario_id=usuario.id).count()
    if ja_teve:
        return False
    # Criar oferta
    # pyrefly: ignore [unexpected-keyword]
    oferta = OfertaTrial(usuario_id=usuario.id)
    db.session.add(oferta)
    usuario.trial_ofertado = True
    db.session.commit()
    return True


# ════════════════════════════════════════════════════
#  HELPERS INTERNOS
# ════════════════════════════════════════════════════

def _verificar_recompensa_nivel(usuario, nivel):
    """Verifica e concede recompensa de nível. Retorna dict ou None."""
    from app.models import RECOMPENSAS_NIVEL, RecompensaNivelConcedida
    if nivel not in RECOMPENSAS_NIVEL:
        return None
    ja = RecompensaNivelConcedida.query.filter_by(
        usuario_id=usuario.id, nivel=nivel).first()
    if ja:
        return None
    rec = RECOMPENSAS_NIVEL[nivel]
    usuario.moedas += rec['moedas']
    if rec['badge'] and not usuario.badge_ativa:
        usuario.badge_ativa = rec['badge']
    if rec['borda'] and not usuario.borda_ativa:
        usuario.borda_ativa = rec['borda']
        # pyrefly: ignore [unexpected-keyword]
    db.session.add(RecompensaNivelConcedida(usuario_id=usuario.id, nivel=nivel))
    return {'nivel': nivel, 'moedas': rec['moedas'],
            'badge': rec['badge'], 'borda': rec['borda']}


# ════════════════════════════════════════════════════
#  SOCIAL — FAVORITAR AMIGO / GRUPO
# ════════════════════════════════════════════════════

@main.route('/social/favoritar/<int:uid>', methods=['POST'])
@login_required
def social_favoritar(uid):
    rel = Amizade.query.filter(
        ((Amizade.solicitante_id == current_user.id) & (Amizade.destinatario_id == uid)) |
        ((Amizade.solicitante_id == uid) & (Amizade.destinatario_id == current_user.id)),
        Amizade.status == 'aceito'
    ).first_or_404()
    if rel.solicitante_id == current_user.id:
        rel.favorito_sol = not rel.favorito_sol
        fav = rel.favorito_sol
    else:
        rel.favorito_dest = not rel.favorito_dest
        fav = rel.favorito_dest
    db.session.commit()
    return jsonify({'ok': True, 'favorito': fav})


@main.route('/social/grupo/<int:grupo_id>/favoritar', methods=['POST'])
@login_required
def grupo_favoritar(grupo_id):
    membro = GrupoMembro.query.filter_by(
        grupo_id=grupo_id, usuario_id=current_user.id).first_or_404()
    membro.favorito = not membro.favorito
    db.session.commit()
    return jsonify({'ok': True, 'favorito': membro.favorito})


@main.route('/social/grupo/<int:grupo_id>/sair', methods=['POST'])
@login_required
def grupo_sair(grupo_id):
    grupo = GrupoChat.query.get_or_404(grupo_id)
    membro = GrupoMembro.query.filter_by(
        grupo_id=grupo_id, usuario_id=current_user.id).first_or_404()
    db.session.delete(membro)
    # Se ficou vazio, deletar grupo
    if GrupoMembro.query.filter_by(grupo_id=grupo_id).count() == 0:
        db.session.delete(grupo)
    db.session.commit()
    return jsonify({'ok': True})


@main.route('/social/grupo/<int:grupo_id>/apagar', methods=['POST'])
@login_required
def grupo_apagar(grupo_id):
    grupo = GrupoChat.query.get_or_404(grupo_id)
    if grupo.criador_id != current_user.id and not current_user.is_admin:
        abort(403)
    db.session.delete(grupo)
    db.session.commit()
    return jsonify({'ok': True})


@main.route('/social/grupo/<int:grupo_id>/config', methods=['GET', 'POST'])
@login_required
def grupo_config(grupo_id):
    from app.models import GrupoConfig
    grupo = GrupoChat.query.get_or_404(grupo_id)
    membro = GrupoMembro.query.filter_by(
        grupo_id=grupo_id, usuario_id=current_user.id, eh_admin=True).first()
    if not membro and grupo.criador_id != current_user.id:
        abort(403)

    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        nome = sanitizar_texto(data.get('nome', grupo.nome), 100)
        icone = data.get('icone', grupo.icone) or '\U0001F4AC'
        grupo.nome = nome
        grupo.icone = icone

        # Adicionar membros
        for uid in data.get('adicionar', []):
            if not GrupoMembro.query.filter_by(grupo_id=grupo_id, usuario_id=uid).first():
                # pyrefly: ignore [unexpected-keyword]
                db.session.add(GrupoMembro(grupo_id=grupo_id, usuario_id=uid))

        # Remover membros
        for uid in data.get('remover', []):
            if uid != grupo.criador_id:  # não remover criador
                m = GrupoMembro.query.filter_by(grupo_id=grupo_id, usuario_id=uid).first()
                if m: db.session.delete(m)

        db.session.commit()
        return jsonify({'ok': True, 'nome': grupo.nome, 'icone': grupo.icone})

    membros = GrupoMembro.query.filter_by(grupo_id=grupo_id).all()
    amigos = []
    for aid in amigos_ids(current_user.id):
        u = Usuario.query.get(aid)
        if u: amigos.append({'id': u.id, 'nome': u.nome_completo,
                              'username': u.username, 'tag': u.tag_exibida})
    return jsonify({
        'nome': grupo.nome, 'icone': grupo.icone,
        'membros': [{'id': m.usuario_id, 'nome': m.usuario.nome_completo,
                     'eh_admin': m.eh_admin} for m in membros],
        'amigos': amigos
    })


@main.route('/social/grupo/<int:grupo_id>/membros')
@login_required
def grupo_membros(grupo_id):
    grupo = GrupoChat.query.get_or_404(grupo_id)
    membro = GrupoMembro.query.filter_by(
        grupo_id=grupo_id, usuario_id=current_user.id).first()
    if not membro: abort(403)
    membros = GrupoMembro.query.filter_by(grupo_id=grupo_id).all()
    return jsonify({'membros': [
        {'id': m.usuario_id, 'nome': m.usuario.nome_completo,
         'username': m.usuario.username, 'tag': m.usuario.tag_exibida,
         'eh_admin': m.eh_admin, 'icon_emoji': m.usuario.icon_emoji}
        for m in membros
    ]})


# ════════════════════════════════════════════════════
#  SOCIAL — RECOMENDAÇÕES DE AMIZADE
# ════════════════════════════════════════════════════

@main.route('/social/sugestoes')
@login_required
def social_sugestoes():
    """Algoritmo de recomendação de amizades."""
    meus_amigos = amigos_ids(current_user.id)
    todas_amizades = set(list(meus_amigos) + [current_user.id])

    candidatos = {}

    # 1. Amigos de amigos (maior peso)
    for amid in meus_amigos:
        amigos_do_amigo = amigos_ids(amid)
        for uid in amigos_do_amigo:
            if uid not in todas_amizades:
                candidatos[uid] = candidatos.get(uid, 0) + 3

    # 2. Mesmas matérias favoritas
    # Pegar matérias mais respondidas pelo usuário atual
    from sqlalchemy import func
    minhas_mat = (db.session.query(Questao.materia_id, func.count(RespostaUsuario.id).label('cnt'))
                  .join(RespostaUsuario, RespostaUsuario.questao_id == Questao.id)
                  .filter(RespostaUsuario.usuario_id == current_user.id)
                  .group_by(Questao.materia_id)
                  .order_by(db.text('cnt DESC')).limit(3).all())
    mat_ids = [m.materia_id for m in minhas_mat]

    if mat_ids:
        outros_usuarios = (db.session.query(RespostaUsuario.usuario_id, func.count().label('cnt'))
                           .join(Questao, Questao.id == RespostaUsuario.questao_id)
                           .filter(Questao.materia_id.in_(mat_ids),
                                   RespostaUsuario.usuario_id != current_user.id)
                           .group_by(RespostaUsuario.usuario_id)
                           .order_by(db.text('cnt DESC')).limit(20).all())
        for row in outros_usuarios:
            if row.usuario_id not in todas_amizades:
                candidatos[row.usuario_id] = candidatos.get(row.usuario_id, 0) + 2

    # 3. Nível similar
    nivel_min = max(1, current_user.nivel - 2)
    nivel_max = current_user.nivel + 2
    nivel_similar = Usuario.query.filter(
        Usuario.id.notin_(list(todas_amizades)),
        Usuario.nivel >= nivel_min,
        Usuario.nivel <= nivel_max
    ).limit(15).all()
    for u in nivel_similar:
        candidatos[u.id] = candidatos.get(u.id, 0) + 1

    # Ordenar por pontuação
    top_ids = sorted(candidatos, key=lambda x: candidatos[x], reverse=True)[:8]
    sugestoes = []
    for uid in top_ids:
        u = Usuario.query.get(uid)
        if u and not u.is_banido:
            sugestoes.append({
                'id': u.id, 'nome': u.nome_completo,
                'username': u.username, 'tag': u.tag_exibida,
                'nivel': u.nivel, 'icon_emoji': u.icon_emoji,
                'score': candidatos[uid]
            })

    return jsonify({'sugestoes': sugestoes})


# ════════════════════════════════════════════════════
#  ANÁLISE DE DESEMPENHO (gráficos avançados)
# ════════════════════════════════════════════════════

@main.route('/api/desempenho/<int:uid>')
@login_required
def api_desempenho(uid):
    """Dados completos de desempenho para gráficos interativos."""
    usuario = Usuario.query.get_or_404(uid)
    # Só o próprio usuário ou se mostrar_stats = True
    if uid != current_user.id and not usuario.mostrar_stats:
        return jsonify({'erro': 'Privado'}), 403

    from sqlalchemy import func
    from datetime import date as d_type, timedelta as td

    # 1. Evolução de XP nos últimos 30 dias
    xp_por_dia = []
    xp_acum = 0
    for i in range(29, -1, -1):
        dia = d_type.today() - td(days=i)
        ganho = db.session.query(func.sum(RespostaUsuario.xp_ganho)).filter(
            RespostaUsuario.usuario_id == uid,
            func.date(RespostaUsuario.data_resposta) == dia
        ).scalar() or 0
        xp_acum += ganho
        xp_por_dia.append({'dia': dia.strftime('%d/%m'), 'xp': ganho, 'xp_acum': xp_acum})

    # 2. Por matéria (stackável)
    materias = Materia.query.all()
    por_materia = []
    for m in materias:
        ids_q = [q.id for q in m.questoes.all()]
        if not ids_q: continue
        total = RespostaUsuario.query.filter(
            RespostaUsuario.usuario_id == uid,
            RespostaUsuario.questao_id.in_(ids_q)).count()
        acerto = RespostaUsuario.query.filter(
            RespostaUsuario.usuario_id == uid,
            RespostaUsuario.questao_id.in_(ids_q),
            RespostaUsuario.acertou == True).count()
        if not total: continue
        # Últimos 7 dias por matéria
        hist = []
        for i in range(6, -1, -1):
            dia = d_type.today() - td(days=i)
            t = RespostaUsuario.query.filter(
                RespostaUsuario.usuario_id == uid,
                RespostaUsuario.questao_id.in_(ids_q),
                func.date(RespostaUsuario.data_resposta) == dia).count()
            a = RespostaUsuario.query.filter(
                RespostaUsuario.usuario_id == uid,
                RespostaUsuario.questao_id.in_(ids_q),
                RespostaUsuario.acertou == True,
                func.date(RespostaUsuario.data_resposta) == dia).count()
            hist.append({'dia': dia.strftime('%d/%m'), 'total': t, 'acertos': a})
        por_materia.append({
            'id': m.id, 'nome': m.nome, 'cor': m.cor, 'icone': m.icone,
            'total': total, 'acertos': acerto, 'erros': total - acerto,
            'pct': round(acerto/total*100, 1),
            'historico': hist
        })

    # 3. Por dificuldade
    por_dificuldade = []
    for dif in ['facil', 'medio', 'dificil']:
        ids_q = [q.id for q in Questao.query.filter_by(dificuldade=dif).all()]
        if not ids_q: continue
        total  = RespostaUsuario.query.filter(
            RespostaUsuario.usuario_id == uid,
            RespostaUsuario.questao_id.in_(ids_q)).count()
        acerto = RespostaUsuario.query.filter(
            RespostaUsuario.usuario_id == uid,
            RespostaUsuario.questao_id.in_(ids_q),
            RespostaUsuario.acertou == True).count()
        if total:
            por_dificuldade.append({
                'dificuldade': dif,
                'total': total, 'acertos': acerto,
                'pct': round(acerto/total*100, 1)
            })

    # 4. Evolução do nível (histórico)
    nivel_hist = []
    xp_corrido = 0
    for i in range(29, -1, -1):
        dia = d_type.today() - td(days=i)
        ganho = db.session.query(func.sum(RespostaUsuario.xp_ganho)).filter(
            RespostaUsuario.usuario_id == uid,
            func.date(RespostaUsuario.data_resposta) == dia
        ).scalar() or 0
        xp_corrido += ganho
        limites = [100,300,600,1000,1500,2500,4000,6000,9000,99999]
        nivel = next((i+1 for i,lim in enumerate(limites) if xp_corrido < lim), 10)
        nivel_hist.append({'dia': dia.strftime('%d/%m'), 'nivel': nivel})

    return jsonify({
        'xp_por_dia': xp_por_dia,
        'por_materia': por_materia,
        'por_dificuldade': por_dificuldade,
        'nivel_historico': nivel_hist,
        'total_geral': usuario.total_respostas,
        'acertos_geral': usuario.total_acertos,
        'pct_geral': usuario.percentual_acerto,
        'streak_atual': usuario.streak.sequencia_atual if usuario.streak else 0,
        'maior_streak': usuario.streak.maior_sequencia if usuario.streak else 0,
    })


# ════════════════════════════════════════════════════
#  MODERAÇÃO DE ARQUIVOS (chat)
# ════════════════════════════════════════════════════

def moderar_arquivo(arquivo, nome_original: str) -> tuple[bool, str]:
    """
    Valida e modera arquivo de chat.
    Retorna (permitido, motivo_bloqueio).
    """
    from app.security import validar_arquivo_imagem, validar_texto_seguro
    import os

    EXTENSOES_PERMITIDAS = {
        'imagem': {'.png','.jpg','.jpeg','.webp','.gif'},
        'documento': {'.pdf','.docx','.doc','.zip','.txt'},
    }
    ALL_EXT = set().union(*EXTENSOES_PERMITIDAS.values())

    ext = os.path.splitext(nome_original)[1].lower()
    if ext not in ALL_EXT:
        return False, f'Extensão "{ext}" não permitida.'

    # Tamanho máx 10MB
    arquivo.seek(0, 2)
    size = arquivo.tell()
    arquivo.seek(0)
    if size > 10 * 1024 * 1024:
        return False, 'Arquivo muito grande. Máximo: 10MB.'

    # Para imagens: validar MIME
    if ext in EXTENSOES_PERMITIDAS['imagem']:
        ok, msg = validar_arquivo_imagem(arquivo)
        if not ok: return False, msg

    # Verificar nome do arquivo por conteúdo suspeito
    ok_nome, msg_nome = validar_texto_seguro(nome_original)
    if not ok_nome:
        return False, f'Nome de arquivo indevido: {msg_nome}'

    return True, ''
