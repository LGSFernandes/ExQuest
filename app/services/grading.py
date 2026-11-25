"""Correção e recompensa de respostas.

Regras:
    - XP e moedas só na PRIMEIRA resposta correta de cada questão por usuário (chave `resposta:{uid}:{qid}`),
    decidida pela unicidade do banco; repetir a questão treina, mas não rende recompensa.
    - O tempo da resposta é medido pelo servidor; o valor enviado pelo navegador é ignorado.
    - Erros entram na fila de revisão espaçada.
    - Respostas muito rápidas só geram registro de auditoria (sinalização). Nunca banem a conta automaticamente.
"""
import math
import random
import re
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import select

from app import clock
from app.extensions import db
from app.models import RespostaUsuario, RevisaoQuestao
from app.services import audit, notificacoes, streak, wallet, xp

_STOP = {"que", "uma", "para", "com", "por", "como", "mais", "mas", "não", "sim", "ser", "ter", "seu", "sua", "dos",
         "das", "nos", "nas", "pelo", "pela", "isso", "isto", "esse", "essa", "ele", "ela", "eles", "elas", "pode",
         "pois", "também"}
LIMIAR_DISCURSIVA = 0.55
TEMPO_MINIMO_SUSPEITO_MS = 1500


def _tokens(txt: str) -> list[str]:
    txt = re.sub(r"[^\w\s]|_", " ", (txt or "").lower())
    return [w for w in txt.split() if len(w) > 2 and w not in _STOP]


def _cos(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0
    vocab = set(a) | set(b)
    idf = {w: math.log(3 / ((w in a) + (w in b) + 1)) + 1 for w in vocab}
    va = [a.count(w) / len(a) * idf[w] for w in vocab]
    vb = [b.count(w) / len(b) * idf[w] for w in vocab]
    norma = math.sqrt(sum(x * x for x in va)) * math.sqrt(sum(y * y for y in vb))
    return sum(x * y for x, y in zip(va, vb)) / norma if norma else 0.0


def avaliar_discursiva(enunciado: str, gabarito: str | None, resposta: str) -> tuple[bool, float, str]:
    """Avaliador local (similaridade textual). Devolve (acertou, nota 0..1, feedback).
    shortcut: sem modelo de linguagem; só mede vocabulário em comum com o gabarito. Para correção semântica, plugar um LLM aqui."""
    if not (gabarito or "").strip():
        ok = len(resposta.split()) >= 10
        return ok, 0.7 if ok else 0.2, ("Resposta registrada. Esta questão não tem gabarito cadastrado." if ok
                                         else "Resposta curta demais. Desenvolva mais.")
    g, r, q = _tokens(gabarito), _tokens(resposta), set(_tokens(enunciado))
    sg, sr = set(g), set(r)
    jac = len(sg & sr) / len(sg | sr) if (sg | sr) else 0.0
    cob = len(q & sr) / len(q) if q else 0.0
    falta = max(0, len(g) - len(r)) / max(len(g), 1)
    nota = round(min((_cos(g, r) * 0.55 + jac * 0.30 + cob * 0.15) * (1 - falta * 0.4), 1.0), 3)
    pct = int(nota * 100)
    if nota >= 0.85:
        fb = f"Cobre os conceitos principais com precisão ({pct}%)."
    elif nota >= 0.70:
        fb = f"Boa resposta; aprofunde alguns conceitos ({pct}%)."
    elif nota >= LIMIAR_DISCURSIVA:
        fb = f"Parcialmente correta ({pct}%). Revise os conceitos principais."
    elif nota >= 0.30:
        fb = f"Faltam elementos importantes ({pct}%). Compare com o gabarito."
    else:
        fb = f"Muito diferente do esperado ({pct}%). Estude o conteúdo e tente de novo."
    return nota >= LIMIAR_DISCURSIVA, nota, fb


def calcular_recompensa(questao, usuario, nota: float = 1.0) -> tuple[int, int]:
    a, b = questao.xp_recompensa
    c, d = questao.moedas_recompensa
    xp_base = int(random.randint(a, b) * nota)
    mo_base = int(random.randint(c, d) * nota)
    return int(xp_base * (1 + usuario.boost_xp_atual / 100)), int(mo_base * (1 + usuario.boost_moeda_atual / 100))


@dataclass
class Resultado:
    acertou: bool
    xp: int = 0
    moedas: int = 0
    nota: float | None = None
    feedback: str | None = None
    primeira_vez: bool = False
    subiu_nivel: bool = False
    recompensas_nivel: list = field(default_factory=list)


def _agendar_revisao(usuario_id: int, questao_id: int) -> None:
    amanha = clock.agora() + timedelta(days=1)
    r = db.session.scalar(select(RevisaoQuestao).where(RevisaoQuestao.usuario_id == usuario_id,
                                                      RevisaoQuestao.questao_id == questao_id))
    if r is None:
        db.session.add(RevisaoQuestao(usuario_id=usuario_id, questao_id=questao_id, proxima_em=amanha, origem="erro",
                                      ultima_em=clock.agora()))
    else:
        r.lapsos += 1
        r.repeticoes = 0
        r.intervalo_dias = 1
        r.facilidade = max(1.3, (r.facilidade or 2.5) - 0.2)
        r.proxima_em, r.ativo, r.ultima_em = amanha, True, clock.agora()


def registrar(usuario, questao, *, acertou: bool, modo: str, alternativa_id=None, texto=None, nota=None,
              feedback=None, simulado_id=None, tempo_ms=None, ip_request=None,
              recompensar=True) -> Resultado:
    """Grava a resposta, concede recompensa (1ª correta) e atualiza streak e revisão. O chamador faz o commit."""
    res = Resultado(acertou=acertou, nota=nota, feedback=feedback)
    if tempo_ms is not None and tempo_ms < TEMPO_MINIMO_SUSPEITO_MS:
        audit.registrar("resposta_rapida", usuario.id, f"q={questao.id} t={tempo_ms}ms", "suspeito", request=ip_request)
    if acertou and recompensar:
        ja = db.session.scalar(select(RespostaUsuario.id).where(
            RespostaUsuario.usuario_id == usuario.id, RespostaUsuario.questao_id == questao.id,
            RespostaUsuario.acertou.is_(True)).limit(1))
        if not ja:
            xp_g, mo_g = calcular_recompensa(questao, usuario, nota if nota is not None else 1.0)
            chave = f"resposta:{usuario.id}:{questao.id}"
            rx = xp.conceder_xp(usuario, xp_g, "resposta", chave, referencia=questao.id)
            if not rx.repetido:  # a unicidade do banco é a palavra final (requisições simultâneas)
                res.primeira_vez, res.xp = True, rx.concedido
                res.subiu_nivel, res.recompensas_nivel = rx.subiu, rx.recompensas
                if rx.subiu:
                    notificacoes.criar(usuario.id, "nivel", f"Você subiu para o nível {usuario.nivel}", None, "/perfil")
                if mo_g > 0:
                    wallet.creditar(usuario.id, mo_g, "resposta", chave, descricao="Questão respondida corretamente",
                                    ref_tipo="questao", ref_id=questao.id)
                    res.moedas = mo_g
        streak.registrar_atividade(usuario)
    elif acertou:
        streak.registrar_atividade(usuario)
    else:
        _agendar_revisao(usuario.id, questao.id)
    db.session.add(RespostaUsuario(usuario_id=usuario.id, questao_id=questao.id, alternativa_id=alternativa_id,
                                   resposta_texto=texto, acertou=acertou, feedback_ia=feedback, nota_ia=nota,
                                   xp_ganho=res.xp, moedas_ganhas=res.moedas, modo=modo, simulado_id=simulado_id,
                                   tempo_ms=tempo_ms))
    db.session.flush()
    db.session.refresh(usuario, ["moedas", "xp"])
    return res
