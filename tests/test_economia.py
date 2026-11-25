import threading
from datetime import timedelta

import pytest

from app import clock
from app.extensions import db
from app.models import ItemLoja, RecompensaNivelConcedida, Usuario
from app.services import inventory, limits, streak, wallet, xp


def novo_usuario(app, nome="ana", moedas=0, xpv=0, **kw):
    u = Usuario(nome="A", sobrenome="B", username=nome, email=f"{nome}@x.com", tag=nome[:4].upper().ljust(4, "X"),
                moedas=moedas, xp=xpv, **kw)
    db.session.add(u)
    db.session.commit()
    return u


# ── carteira ─────────────────────────────────────────────
def test_credito_e_debito_deixam_ledger_consistente(app):
    u = novo_usuario(app, moedas=0)
    wallet.creditar(u.id, 100, "recompensa", "k1")
    wallet.debitar(u.id, 30, "compra_item", "k2")
    db.session.commit()
    assert u.moedas == 70
    assert wallet.conferir(u.id) == (True, 70, 70)


def test_debito_sem_saldo_nao_altera_nada(app):
    u = novo_usuario(app, moedas=10)
    with pytest.raises(wallet.SaldoInsuficiente):
        wallet.debitar(u.id, 11, "compra_item", "k")
    db.session.rollback()
    assert db.session.get(Usuario, u.id).moedas == 10


def test_mesma_chave_nao_aplica_duas_vezes(app):
    u = novo_usuario(app)
    a = wallet.creditar(u.id, 50, "recompensa", "pagamento:7")
    b = wallet.creditar(u.id, 50, "recompensa", "pagamento:7")
    db.session.commit()
    assert a.novo and not b.novo and u.moedas == 50


def test_valor_invalido_e_rejeitado(app):
    u = novo_usuario(app)
    for v in (0, -5):
        with pytest.raises(ValueError):
            wallet.creditar(u.id, v, "x", f"k{v}")


def test_saldo_legado_nulo_funciona(app):
    u = novo_usuario(app)
    db.session.execute(db.text("update usuarios set moedas=NULL where id=:i"), {"i": u.id})
    db.session.commit()
    wallet.creditar(u.id, 5, "bonus", "k")
    db.session.commit()
    assert db.session.get(Usuario, u.id).moedas == 5


# ── XP e níveis ──────────────────────────────────────────
def test_xp_idempotente_e_sobe_nivel_com_recompensa_unica(app):
    db.session.add(ItemLoja(slug="badge-veterano", nome="Badge Veterano", descricao="d", tipo="badge", preco=1))
    u = novo_usuario(app, xpv=900)  # nível 4 (600..999)
    r = xp.conceder_xp(u, 200, "resposta", "r:1")  # 1100 -> nível 5 (30 moedas)
    db.session.commit()
    assert (r.nivel_antes, r.nivel_depois) == (4, 5) and r.concedido == 200
    assert [x["nivel"] for x in r.recompensas] == [5] and u.moedas == 30
    r2 = xp.conceder_xp(u, 200, "resposta", "r:1")  # mesma chave
    assert r2.repetido and u.xp == 1100 and u.moedas == 30
    assert RecompensaNivelConcedida.query.count() == 1


def test_recompensa_de_nivel_com_item(app):
    db.session.add(ItemLoja(slug="badge-veterano", nome="Badge Veterano", descricao="d", tipo="badge", preco=1))
    u = novo_usuario(app, xpv=niveis_xp(19))
    xp.conceder_xp(u, 10_000, "teste", "t:1")  # passa do 20
    db.session.commit()
    from app.models import InventarioItem
    assert InventarioItem.query.filter_by(usuario_id=u.id).count() == 1


def niveis_xp(n):
    from app.services import niveis
    return niveis.xp_inicio_do_nivel(n)


# ── inventário ───────────────────────────────────────────
def test_conceder_cosmetico_duas_vezes_mantem_uma_linha_e_consumivel_acumula(app):
    borda = ItemLoja(slug="borda-prata", nome="Prata", descricao="d", tipo="borda", preco=1)
    boost = ItemLoja(slug="boost-xp-50", nome="Boost", descricao="d", tipo="boost_xp", preco=1)
    db.session.add_all([borda, boost])
    u = novo_usuario(app)
    inventory.conceder(u.id, borda)
    inventory.conceder(u.id, borda)
    inventory.conceder(u.id, boost)
    i = inventory.conceder(u.id, boost)
    db.session.commit()
    from app.models import InventarioItem
    assert InventarioItem.query.filter_by(usuario_id=u.id).count() == 2 and i.quantidade == 2


# ── streak ───────────────────────────────────────────────
def _dias_atras(n):
    return clock.hoje() - timedelta(days=n)


def test_streak_basico(app):
    u = novo_usuario(app)
    s = streak.registrar_atividade(u)
    assert s.sequencia_atual == 1
    streak.registrar_atividade(u)  # mesmo dia
    assert u.streak.sequencia_atual == 1
    u.streak.ultima_atividade = _dias_atras(1)
    streak.registrar_atividade(u)
    assert u.streak.sequencia_atual == 2 and u.streak.maior_sequencia == 2


def test_streak_quebra_sem_escudo_e_escudo_cobre_dia_perdido(app):
    u = novo_usuario(app)
    s = streak.obter(u)
    s.sequencia_atual, s.maior_sequencia, s.ultima_atividade = 5, 5, _dias_atras(3)  # perdeu 2 dias
    streak.registrar_atividade(u)
    assert u.streak.sequencia_atual == 1 and u.streak.maior_sequencia == 5
    u.streak.sequencia_atual, u.streak.ultima_atividade, u.streak.escudos = 5, _dias_atras(3), 2
    streak.registrar_atividade(u)
    assert u.streak.sequencia_atual == 6 and u.streak.escudos == 0
    u.streak.sequencia_atual, u.streak.ultima_atividade, u.streak.escudos = 5, _dias_atras(4), 1  # perdeu 3, tem 1
    streak.registrar_atividade(u)
    assert u.streak.sequencia_atual == 1 and u.streak.escudos == 0


def test_streak_legado_protegido_vira_escudo(app):
    u = novo_usuario(app)
    s = streak.obter(u)
    s.sequencia_atual, s.ultima_atividade, s.streak_protegido = 4, _dias_atras(2), True
    streak.registrar_atividade(u)
    assert u.streak.sequencia_atual == 5 and u.streak.streak_protegido is False


def test_streak_exibida_zera_quando_ja_perdeu(app):
    u = novo_usuario(app)
    s = streak.obter(u)
    s.sequencia_atual, s.ultima_atividade = 7, _dias_atras(3)
    assert streak.sequencia_exibida(s) == (0, False, False)
    s.ultima_atividade = _dias_atras(1)
    assert streak.sequencia_exibida(s) == (7, False, True)


# ── limites ──────────────────────────────────────────────
def test_limite_diario_gratuito_e_bonus(app):
    u = novo_usuario(app, questoes_bonus=1)
    assert [limits.consumir_questao(u) for _ in range(5)] == [True, True, True, True, False]  # 3 + 1 bônus
    assert db.session.get(Usuario, u.id).questoes_bonus == 0
    assert limits.restante_questoes(u) == 0


def test_limite_reseta_no_dia_seguinte(app):
    u = novo_usuario(app)
    for _ in range(3):
        limits.consumir_questao(u)
    assert not limits.consumir_questao(u)
    u.ultimo_reset = _dias_atras(1)
    db.session.commit()
    assert limits.consumir_questao(u)


def test_premium_avancado_e_ilimitado(app):
    u = novo_usuario(app, plano_premium="advan", premium_expira=clock.agora() + timedelta(days=5))
    assert all(limits.consumir_questao(u) for _ in range(40))
    assert limits.restante_questoes(u) is None


def test_simulados_por_dia(app):
    u = novo_usuario(app)
    assert limits.consumir_simulado(u) and not limits.consumir_simulado(u)  # gratuito: 1/dia
