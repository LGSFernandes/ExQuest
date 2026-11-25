"""Sequência diária (streak). O "dia" é o de America/Sao_Paulo. Escudos cobrem dias perdidos, um por dia."""
from datetime import timedelta

from app import clock
from app.extensions import db
from app.models import Streak


def obter(usuario) -> Streak:
    s = usuario.streak
    if s is None:
        s = Streak(usuario_id=usuario.id, sequencia_atual=0, maior_sequencia=0, escudos=0)
        db.session.add(s)
        usuario.streak = s
    if s.streak_protegido:  # legado: o antigo "protegido" equivale a 1 escudo
        s.escudos = (s.escudos or 0) + 1
        s.streak_protegido = False
    return s


def registrar_atividade(usuario) -> Streak:
    """Chame quando o usuário conclui uma atividade que conta para o dia. Idempotente no mesmo dia."""
    s = obter(usuario)
    hoje = clock.hoje()
    if s.ultima_atividade == hoje:
        return s
    if s.ultima_atividade is None:
        s.sequencia_atual = 1
    else:
        perdidos = (hoje - s.ultima_atividade).days - 1
        if perdidos <= 0:
            s.sequencia_atual = (s.sequencia_atual or 0) + 1
        elif perdidos <= (s.escudos or 0):
            s.escudos -= perdidos  # cada escudo cobre um dia perdido; a sequência continua
            s.sequencia_atual = (s.sequencia_atual or 0) + 1
        else:
            s.escudos = 0  # escudos não cobrem a falha; perdem-se junto com a sequência
            s.sequencia_atual = 1
    s.ultima_atividade = hoje
    s.maior_sequencia = max(s.maior_sequencia or 0, s.sequencia_atual)
    return s


def sequencia_exibida(streak: Streak | None) -> tuple[int, bool, bool]:
    """(dias, ativa_hoje, em_risco). Se já passou do prazo sem escudo, mostra 0 mesmo antes da próxima atividade."""
    if streak is None or not streak.ultima_atividade:
        return 0, False, False
    hoje = clock.hoje()
    perdidos = (hoje - streak.ultima_atividade).days - 1
    if perdidos < 0:
        return streak.sequencia_atual or 0, True, False
    escudos = (streak.escudos or 0) + (1 if streak.streak_protegido else 0)
    if perdidos == 0:
        return streak.sequencia_atual or 0, False, True  # fez ontem, falta hoje
    if perdidos <= escudos:
        return streak.sequencia_atual or 0, False, True
    return 0, False, False


def adicionar_escudos(usuario, n: int) -> None:
    obter(usuario).escudos += n
