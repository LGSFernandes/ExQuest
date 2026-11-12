"""
ExQuest Security Module
━━━━━━━━━━━━━━━━━━━━━━
Funções de validação, moderação de conteúdo,
sanitização e utilitários de segurança.
"""
import os, re, hashlib, mimetypes
from datetime import datetime, timezone

# ─── Extensões permitidas por categoria ──────────────────────────
ALLOWED_IMAGE_EXT = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
ALLOWED_IMAGE_MIME = {'image/png', 'image/jpeg', 'image/webp', 'image/gif'}
MAX_FILE_SIZE = 5 * 1024 * 1024   # 5 MB

# ─── Listas de termos banidos (básico — em produção use serviço externo) ─

# ============================================================
# EXQUEST — SISTEMA DE MODERAÇÃO DE CONTEÚDO
# ============================================================

# 1. PALAVRÕES E EXPRESSÕES VULGARES
_TERMOS_PALAVROES = [
    "porra",
    "merda",
    "bosta",
    "caralho",
    "cacete",
    "foda-se",
    "foder",
    "fodido",
    "fodida",
    "puta merda",
    "puta que pariu",
    "filho da puta",
    "filha da puta",
    "vai tomar no cu",
    "vai se foder",
    "vai pra puta que pariu",
    "arrombado",
    "arrombada",
    "desgraçado",
    "desgraçada",
    "babaca",
    "otário",
    "otária",
    "escroto",
    "escrota",
    "imbecil",
    "idiota",
    "retardado",
    "retardada",
    "fdp",
    "pqp",
    "vsf",
    "tmnc",
    "cuzao",
    "cuzona",
    "corno",
    "vagabundo",
    "vagabunda",
    "lixo humano",
    "desgraça",
    "inferno",
    "buceta",
    "caralhada",
    "punheta",
    "punheteiro",
    "punheteira",
    "rola",
    "piroca",
    "pica",
    "xoxota",
    "porralouca",
    "cabrão",
    "merdinha",
]

# 2. OFENSAS E HUMILHAÇÕES
_TERMOS_OFENSAS = [
    "você é um lixo",
    "voce e um lixo",
    "você não presta",
    "voce nao presta",
    "ninguém gosta de você",
    "ninguem gosta de voce",
    "você é um fracasso",
    "voce e um fracasso",
    "seu inútil",
    "sua inútil",
    "seu idiota",
    "sua idiota",
    "seu imbecil",
    "sua imbecil",
    "seu verme",
    "sua praga",
    "vai morrer sozinho",
    "ninguém te quer",
    "calar a boca seu idiota",
]

# 3. DISCRIMINAÇÃO E DISCURSO DE ÓDIO
# Utilize também um dicionário especializado e revisado
# para insultos direcionados a grupos protegidos.
_TERMOS_DISCRIMINACAO = [
    "morte aos negros",
    "morte aos imigrantes",
    "morte aos homossexuais",
    "morte aos judeus",
    "morte aos muçulmanos",
    "morte aos cristãos",
    "morte aos deficientes",
    "eliminar todos os",
    "essa raça deveria morrer",
    "essa religião deveria ser exterminada",
    "não deveriam existir",
    "inferiores por natureza",
    "não são seres humanos",
    "devem ser exterminados",
]

# 4. AMEAÇAS E VIOLÊNCIA DIRECIONADA
_TERMOS_AMEACAS = [
    "vou te matar",
    "vou matar você",
    "vou te espancar",
    "vou te torturar",
    "vou te sequestrar",
    "vou te esfaquear",
    "vou te dar um tiro",
    "vou acabar com você",
    "vou acabar com sua vida",
    "vou quebrar sua cara",
    "vou te encontrar e te matar",
    "vou te estuprar",
    "quero te ver morto",
    "quero te ver morta",
    "vou colocar uma bomba",
    "vou explodir sua casa",
    "vou invadir sua casa",
    "vou perseguir você",
    "vou te fazer sofrer",
]

# 5. CONTEÚDO SEXUAL EXPLÍCITO E SOLICITAÇÕES
_TERMOS_SEXUAIS = [
    "pornografia",
    "conteúdo pornográfico",
    "conteudo pornografico",
    "vídeo pornográfico",
    "video pornografico",
    "sexo explícito",
    "sexo explicito",
    "nudes",
    "pack de nudes",
    "vender nudes",
    "comprar nudes",
    "manda nude",
    "manda nudes",
    "troca de nudes",
    "vídeo sexual explícito",
    "video sexual explicito",
    "pornô",
    "porno",
    "site pornô",
    "site porno",
    "material pornográfico",
    "material pornografico",
]

# 6. EXPLORAÇÃO SEXUAL E ALICIAMENTO
# Tratar ocorrências como prioridade crítica de moderação.
_TERMOS_EXPLORACAO = [
    "nudes de menor",
    "pack de menor",
    "nudes de criança",
    "nudes de crianca",
    "pornografia infantil",
    "exploração sexual infantil",
    "exploracao sexual infantil",
    "abuso sexual infantil",
    "aliciar menores",
    "aliciamento de menores",
    "conteúdo sexual de crianças",
    "conteudo sexual de criancas",
    "criança para sexo",
    "crianca para sexo",
]

# 7. INCENTIVO À AUTOMUTILAÇÃO E AO SUICÍDIO
# NÃO bloquear pedidos de ajuda ou relatos de sofrimento.
# Devem ser encaminhados a um fluxo especial de segurança.
_TERMOS_AUTODESTRUTIVOS = [
    "incentive o suicídio",
    "incentive o suicidio",
    "se mate",
    "vai se matar",
    "corte seus pulsos",
    "se automutile",
    "automutilação é boa",
    "automutilacao e boa",
    "incentivar automutilação",
    "incentivar automutilacao",
    "desafio de suicídio",
    "desafio de suicidio",
]

# 8. CRIMES E ATIVIDADES ILÍCITAS
# Priorizar expressões que indiquem intenção de praticar,
# facilitar, vender ou contratar atividades criminosas.
_TERMOS_CRIMES = [
    "roubar uma conta",
    "roubar identidade",
    "roubar senha",
    "roubar cartão",
    "roubar cartao",
    "falsificar documentos",
    "falsificar identidade",
    "falsificar assinatura",
    "lavagem de dinheiro",
    "cometer fraude",
    "aplicar golpe",
    "organizar um golpe",
    "extorquir alguém",
    "extorquir alguem",
    "sequestrar alguém",
    "sequestrar alguem",
    "vender documentos falsos",
    "clonar cartão",
    "clonar cartao",
    "invadir propriedade",
    "invadir residência",
    "invadir residencia",
    "traficar pessoas",
    "contrabandear mercadorias",
    "comprar dados roubados",
    "vender dados roubados",
]

# 9. DROGAS E COMERCIALIZAÇÃO ILÍCITA
_TERMOS_DROGAS = [
    "vender cocaína",
    "vender cocaina",
    "vender crack",
    "vender heroína",
    "vender heroina",
    "vender metanfetamina",
    "vender ecstasy",
    "vender drogas",
    "comprar drogas",
    "distribuir entorpecentes",
    "traficar drogas",
    "comercializar entorpecentes",
    "vender substâncias ilícitas",
    "vender substancias ilicitas",
]

# 10. ARMAS, EXPLOSIVOS E AMEAÇAS
_TERMOS_ARMAS = [
    "vender armas ilegalmente",
    "comprar armas ilegalmente",
    "comercializar armas ilegais",
    "ameaça com arma",
    "ameaca com arma",
    "ameaça de bomba",
    "ameaca de bomba",
    "fabricar explosivos para atacar",
    "atentado com explosivos",
    "ameaçar com explosivos",
    "ameacar com explosivos",
]

# 11. CRIMES DIGITAIS
_TERMOS_CYBERCRIME = [
    "roubar senhas",
    "roubo de credenciais",
    "invadir conta",
    "invadir contas",
    "hackear conta de terceiros",
    "roubar conta de terceiros",
    "clonar whatsapp",
    "clonar whatsapp de alguém",
    "clonar whatsapp de alguem",
    "roubar token",
    "roubar cookies",
    "roubar sessão",
    "roubar sessao",
    "roubar dados pessoais",
    "roubar dados bancários",
    "roubar dados bancarios",
    "phishing",
    "ransomware",
    "spyware",
    "keylogger",
    "distribuir malware",
    "instalar malware",
    "ataque ddos",
    "fraude digital",
    "vender contas roubadas",
    "vender senhas roubadas",
]

# 12. EXTREMISMO E TERRORISMO
_TERMOS_EXTREMISMO = [
    "recrutar para terrorismo",
    "recrutamento terrorista",
    "financiar terrorismo",
    "financiar atentado",
    "planejar atentado",
    "planejar ataque terrorista",
    "incitar terrorismo",
    "organização terrorista",
    "organizacao terrorista",
    "ameaçar civis",
    "ameacar civis",
    "incitar massacre",
    "promover extermínio",
    "promover exterminio",
]

# 13. PRIVACIDADE E EXPOSIÇÃO DE DADOS
_TERMOS_PRIVACIDADE = [
    "vazar endereço",
    "vazar endereco",
    "vazar telefone",
    "vazar cpf",
    "vazar documentos",
    "divulgar dados pessoais",
    "expor dados pessoais",
    "expor endereço residencial",
    "expor endereco residencial",
    "publicar documentos privados",
    "divulgar senha",
    "divulgar informações privadas",
    "divulgar informacoes privadas",
    "doxxar alguém",
    "doxxar alguem",
]

# 14. GOLPES, PHISHING E SPAM
_TERMOS_GOLPES = [
    "roube sua conta",
    "envie sua senha",
    "me passe seu código de verificação",
    "me passe seu codigo de verificacao",
    "falso comprovante",
    "comprovante falso",
    "falso pix",
    "pix falso",
    "golpe financeiro",
    "golpe do pix",
    "roubar dinheiro",
    "duplicar dinheiro",
    "dinheiro fácil garantido",
    "dinheiro facil garantido",
    "clique para ganhar dinheiro garantido",
    "senha bancária",
    "senha bancaria",
]

# 15. GORE E CRUELDADE EXPLÍCITA
_TERMOS_GORE = [
    "vídeo de execução real",
    "video de execucao real",
    "vídeo de decapitação",
    "video de decapitacao",
    "vídeo de tortura real",
    "video de tortura real",
    "morte extremamente explícita",
    "morte extremamente explicita",
    "compartilhar vídeos de execução",
    "compartilhar videos de execucao",
    "crueldade animal explícita",
    "crueldade animal explicita",
]

# 16. CATEGORIAS CONSOLIDADAS
_TERMOS_BANIDOS = (
    _TERMOS_PALAVROES
    + _TERMOS_OFENSAS
    + _TERMOS_DISCRIMINACAO
    + _TERMOS_AMEACAS
    + _TERMOS_SEXUAIS
    + _TERMOS_EXPLORACAO
    + _TERMOS_AUTODESTRUTIVOS
    + _TERMOS_CRIMES
    + _TERMOS_DROGAS
    + _TERMOS_ARMAS
    + _TERMOS_CYBERCRIME
    + _TERMOS_EXTREMISMO
    + _TERMOS_PRIVACIDADE
    + _TERMOS_GOLPES
    + _TERMOS_GORE
)


_PATTERN_BANIDO = re.compile(
    r'(' + '|'.join(re.escape(t) for t in _TERMOS_BANIDOS) + r')',
    re.IGNORECASE
)

# ─── Padrões suspeitos em texto ───────────────────────────────────
_PATTERN_SQL = re.compile(r"(--|;|\/\*|\*\/|xp_|exec\s*\(|union\s+select)", re.I)
_PATTERN_SCRIPT = re.compile(r"<\s*script|javascript:|on\w+=|<\s*iframe", re.I)
_PATTERN_PATH = re.compile(r"\.\./|\.\.\\|%2e%2e", re.I)


def sanitizar_texto(texto: str, max_len: int = 2000) -> str:
    """Remove tags HTML, limita tamanho e escapa caracteres perigosos."""
    import bleach
    if not texto:
        return ''
    limpo = bleach.clean(str(texto), tags=[], attributes={}, strip=True)
    return limpo[:max_len].strip()


def validar_texto_seguro(texto: str) -> tuple[bool, str]:
    """
    Retorna (True, '') se o texto é seguro.
    Retorna (False, motivo) se foi detectado conteúdo indevido.
    """
    if not texto:
        return True, ''
    if _PATTERN_SQL.search(texto):
        return False, 'Possível tentativa de injeção SQL.'
    if _PATTERN_SCRIPT.search(texto):
        return False, 'Conteúdo de script detectado.'
    if _PATTERN_PATH.search(texto):
        return False, 'Tentativa de path traversal detectada.'
    if _PATTERN_BANIDO.search(texto):
        return False, 'Conteúdo inapropriado detectado.'
    return True, ''


def validar_username(username: str) -> tuple[bool, str]:
    """Username: 3–40 chars, alfanumérico + _ + - apenas."""
    if not re.match(r'^[a-zA-Z0-9_\-]{3,40}$', username):
        return False, 'Username deve ter 3–40 caracteres (letras, números, _ ou -).'
    seguro, motivo = validar_texto_seguro(username)
    if not seguro:
        return False, motivo
    return True, ''


def validar_arquivo_imagem(arquivo) -> tuple[bool, str]:
    """
    Valida extensão, MIME type e tamanho de um FileStorage.
    Retorna (True, '') ou (False, motivo).
    """
    if not arquivo or not arquivo.filename:
        return False, 'Nenhum arquivo enviado.'

    ext = os.path.splitext(arquivo.filename)[1].lower()
    if ext not in ALLOWED_IMAGE_EXT:
        return False, f'Extensão não permitida. Use: {", ".join(ALLOWED_IMAGE_EXT)}'

    # Verificar MIME pelo conteúdo (primeiros bytes)
    cabecalho = arquivo.read(512)
    arquivo.seek(0)

    mime = _detectar_mime(cabecalho)
    if mime not in ALLOWED_IMAGE_MIME:
        return False, 'Tipo de arquivo não permitido.'

    # Verificar tamanho
    arquivo.seek(0, 2)
    size = arquivo.tell()
    arquivo.seek(0)
    if size > MAX_FILE_SIZE:
        return False, f'Arquivo muito grande. Máximo: {MAX_FILE_SIZE // 1024 // 1024} MB.'

    return True, ''


def _detectar_mime(cabecalho: bytes) -> str:
    """Detecta MIME pelos magic bytes sem dependência externa."""
    assinaturas = {
        b'\x89PNG\r\n\x1a\n': 'image/png',
        b'\xff\xd8\xff':       'image/jpeg',
        b'GIF87a':             'image/gif',
        b'GIF89a':             'image/gif',
        b'RIFF':               'image/webp',
    }
    for sig, mime in assinaturas.items():
        if cabecalho.startswith(sig):
            return mime
    # WebP tem RIFF????WEBP
    if cabecalho[:4] == b'RIFF' and cabecalho[8:12] == b'WEBP':
        return 'image/webp'
    return 'application/octet-stream'


def nome_arquivo_seguro(filename: str, prefixo: str = '') -> str:
    """Gera nome de arquivo seguro com hash para evitar colisões."""
    ext = os.path.splitext(filename)[1].lower()
    ts = str(datetime.now(timezone.utc).timestamp()).replace('.', '')
    h = hashlib.md5((filename + ts).encode()).hexdigest()[:8]
    return f'{prefixo}{h}{ext}'


def ip_usuario(request) -> str:
    """Extrai IP real considerando proxies."""
    xff = request.headers.get('X-Forwarded-For')
    if xff:
        return xff.split(',')[0].strip()
    return request.remote_addr or 'desconhecido'


def registrar_log(db_session, acao: str, usuario_id=None,
                  detalhe: str = '', ip: str = '',
                  user_agent: str = '', resultado: str = 'ok'):
    """Registra evento no log de auditoria."""
    from app.models import LogAuditoria
    log = LogAuditoria(
        # pyrefly: ignore [unexpected-keyword]
        usuario_id=usuario_id,
        # pyrefly: ignore [unexpected-keyword]
        acao=acao,
        # pyrefly: ignore [unexpected-keyword]
        detalhe=detalhe[:500] if detalhe else '',
        # pyrefly: ignore [unexpected-keyword]
        ip=ip[:50],
        # pyrefly: ignore [unexpected-keyword]
        user_agent=user_agent[:300],
        # pyrefly: ignore [unexpected-keyword]
        resultado=resultado,
    )
    db_session.add(log)
    # Não faz commit aqui — deixa para o chamador controlar a transação
