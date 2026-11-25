from datetime import timedelta

from app import clock
from app.extensions import db
from app.models import Alternativa, LancamentoCarteira, Materia, Questao, RespostaUsuario, Usuario
from app.services import missoes as svc
from tests.test_auth import registrar


def _setup(client, n=5, acertos=5, premium=True):
    registrar(client)
    u = Usuario.query.one()
    if premium:  # o plano gratuito tem meta reduzida (ver teste abaixo)
        u.plano_premium, u.premium_expira = "inter", clock.agora() + timedelta(days=30)
    m = Materia(nome="M"); db.session.add(m); db.session.flush()
    for i in range(n):
        q = Questao(materia_id=m.id, enunciado=f"Q{i}", tipo="multipla", dificuldade="facil", ativo=True)
        db.session.add(q); db.session.flush()
        db.session.add(RespostaUsuario(usuario_id=u.id, questao_id=q.id, acertou=i < acertos))
    db.session.commit()
    return u


def test_progresso_conta_questoes_distintas_e_nao_resgata_antes(client):
    u = _setup(client, n=3, acertos=3)
    q = Questao.query.first()
    for _ in range(4):  # repetir a mesma questão não infla o progresso
        db.session.add(RespostaUsuario(usuario_id=u.id, questao_id=q.id, acertou=True))
    db.session.commit()
    lista = {i["missao"].slug: i for i in svc.listar(u)}
    assert lista["dia-responder-5"]["atual"] == 3 and not lista["dia-responder-5"]["pronta"]
    assert lista["dia-acertar-3"]["pronta"]
    assert client.post("/missoes/dia-responder-5/resgatar").status_code == 302
    assert LancamentoCarteira.query.filter_by(categoria="missao").count() == 0


def test_resgate_paga_uma_vez_e_ignora_respostas_de_ontem(client):
    u = _setup(client, n=5, acertos=5)
    antes = u.xp or 0
    assert client.get("/missoes/").status_code == 200
    client.post("/missoes/dia-responder-5/resgatar"); client.post("/missoes/dia-responder-5/resgatar")
    db.session.refresh(u)
    assert u.xp - antes == svc.POR_SLUG["dia-responder-5"].xp
    assert LancamentoCarteira.query.filter_by(categoria="missao").count() == 1
    assert client.post("/missoes/nao-existe/resgatar").status_code == 302
    for r in RespostaUsuario.query.all():
        r.data_resposta = clock.agora() - timedelta(days=2)
    db.session.commit()
    assert {i["missao"].slug: i["atual"] for i in svc.listar(u)}["dia-responder-5"] == 0


def test_plano_gratuito_tem_meta_alcancavel_dentro_do_limite_diario(client):
    u = _setup(client, n=3, acertos=3, premium=False)  # gratuito: 3 questões por dia
    lista = {i["missao"].slug: i for i in svc.listar(u)}
    assert lista["dia-responder-5"]["meta"] == 3 and lista["dia-responder-5"]["pronta"]
    assert lista["dia-acertar-3"]["meta"] == 2 and lista["semana-responder-30"]["meta"] == 21
    assert "3 questões" in lista["dia-responder-5"]["descricao"]
    assert lista["semana-dias-5"]["meta"] == 5  # dias distintos não dependem do limite diário
