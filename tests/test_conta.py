from datetime import timedelta

from app import clock
import pytest
import json

from app.extensions import db
from app.models import Amizade, Colecao, LancamentoCarteira, Mensagem, Notificacao, Pagamento, Usuario
from tests.test_auth import DADOS, registrar


def _pag(uid, status):
    return Pagamento(usuario_id=uid, provider="stripe", tipo="premium", produto_ref="inter:mensal", descricao="x", valor_centavos=100,
                     status=status, chave_idempotencia=f"k{uid}{status}")


def test_exportar_inclui_pagamentos_e_carteira_reais(client):
    registrar(client)
    uid = Usuario.query.one().id
    db.session.add_all([_pag(uid, "aprovado"), LancamentoCarteira(usuario_id=uid, tipo="credito", valor=5, saldo_apos=5, categoria="teste", chave_idempotencia="e1"),
                        Colecao(usuario_id=uid, nome="C")])
    db.session.commit()
    d = json.loads(client.get("/configuracoes/meus-dados").data)
    assert d["pagamentos"][0]["provedor"] == "stripe" and d["carteira"][0]["valor"] == 5 and d["colecoes"][0]["nome"] == "C"


def test_exportar_dados_retorna_json_do_proprio_usuario(client):
    registrar(client)
    r = client.get("/configuracoes/meus-dados")
    assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"] and "no-store" in r.headers["Cache-Control"]
    d = json.loads(r.data)
    assert d["conta"]["email"] == Usuario.query.one().email and "senha_hash" not in r.data.decode()
    assert set(d) >= {"respostas", "carteira", "pagamentos", "colecoes", "mensagens_enviadas"}


def test_exportar_exige_login(client):
    assert client.get("/configuracoes/meus-dados").status_code in (302, 401)


def test_excluir_conta_exige_confirmacao_e_senha(client):
    registrar(client)
    assert client.post("/configuracoes/excluir-conta", data={"confirmacao": "talvez", "senha": "x"}).status_code == 302
    assert Usuario.query.one().is_banido is False
    client.post("/configuracoes/excluir-conta", data={"confirmacao": "EXCLUIR", "senha": "senha-errada-123"})
    assert Usuario.query.one().is_banido is False


def test_excluir_conta_anonimiza_e_preserva_financeiro(client, app):
    registrar(client)
    u = Usuario.query.one()
    uid, email = u.id, u.email
    db.session.add(Notificacao(usuario_id=uid, tipo="x", titulo="t"))
    db.session.add(Colecao(usuario_id=uid, nome="Minha"))
    db.session.add(LancamentoCarteira(usuario_id=uid, tipo="credito", valor=10, saldo_apos=10, categoria="teste", chave_idempotencia=f"t:{uid}"))
    db.session.commit()
    client.post("/configuracoes/excluir-conta", data={"confirmacao": "excluir", "senha": DADOS["senha"]})
    u = db.session.get(Usuario, uid)
    assert u.is_banido and u.email != email and u.nome == "Conta" and u.senha_hash is None
    assert Notificacao.query.filter_by(usuario_id=uid).count() == 0 and Colecao.query.filter_by(usuario_id=uid).count() == 0
    assert LancamentoCarteira.query.filter_by(usuario_id=uid).count() == 1  # histórico financeiro permanece
    assert client.get("/missoes/").status_code == 302  # a sessão não vale mais
    assert Usuario.query.filter_by(email=email).count() == 0  # o e-mail ficou livre para um novo cadastro
    assert client.post("/entrar", data={"email": email, "senha": DADOS["senha"]}).status_code != 302


def test_admin_e_pagamento_pendente_impedem_exclusao(client):
    registrar(client)
    u = Usuario.query.one()
    u.is_admin = True; db.session.commit()
    r = client.post("/configuracoes/excluir-conta", data={"confirmacao": "EXCLUIR", "senha": DADOS["senha"]}, follow_redirects=True)
    assert "administrador" in r.data.decode() and not db.session.get(Usuario, u.id).is_banido
    u.is_admin = False
    db.session.add(_pag(u.id, "pendente"))
    db.session.commit()
    r = client.post("/configuracoes/excluir-conta", data={"confirmacao": "EXCLUIR", "senha": DADOS["senha"]}, follow_redirects=True)
    assert "pagamento pendente" in r.data.decode() and not db.session.get(Usuario, u.id).is_banido


def test_exclusao_remove_o_nome_dos_avisos_de_outras_pessoas(app):
    from app.models import Notificacao
    from app.services import notificacoes
    a = Usuario(username="a1", email="a1@x.com", nome="Beatriz", sobrenome="S", tag="0001", senha_hash="x")
    b = Usuario(username="b1", email="b1@x.com", nome="Caio", sobrenome="S", tag="0002", senha_hash="x")
    db.session.add_all([a, b]); db.session.flush()
    notificacoes.criar(b.id, "amizade", "Novo pedido de amizade", "Beatriz quer ser seu amigo.", "/amigos")
    db.session.commit()
    from app.services import conta
    conta.excluir(a); db.session.commit()
    assert "Beatriz" not in Notificacao.query.filter_by(usuario_id=b.id).one().corpo


def test_quem_recusou_pode_pedir_depois_mas_o_recusado_nao_insiste(app):
    from app.services import amizades
    a = Usuario(username="a2", email="a2@x.com", nome="Ana", sobrenome="S", tag="0003", senha_hash="x")
    b = Usuario(username="b2", email="b2@x.com", nome="Bia", sobrenome="S", tag="0004", senha_hash="x")
    db.session.add_all([a, b]); db.session.flush()
    amizades.pedir(a, b); db.session.flush()
    amizades.recusar(b, amizades.relacao(a.id, b.id)); db.session.flush()
    with pytest.raises(amizades.ErroSocial):
        amizades.pedir(a, b)
    assert amizades.pedir(b, a) == "enviado"


def test_upload_respeita_a_orientacao_exif(app, tmp_path):
    import io
    from PIL import Image
    from werkzeug.datastructures import FileStorage
    from app.services import uploads
    im = Image.new("RGB", (40, 20), "red")
    ex = Image.Exif(); ex[0x0112] = 6  # gira 90 graus
    buf = io.BytesIO(); im.save(buf, "JPEG", exif=ex)
    app.config["UPLOAD_ROOT"] = str(tmp_path)
    nome = uploads.salvar_imagem(FileStorage(io.BytesIO(buf.getvalue()), filename="a.jpg"), "icon", permitir_gif=False)
    assert Image.open(tmp_path / "icon" / nome).size == (20, 40)


def test_perfil_so_lista_amigos_se_a_pessoa_permitir(client):
    from app.services import amizades
    registrar(client)
    me = Usuario.query.filter_by(email=DADOS["email"].lower()).one()
    f = Usuario(username="amigo9", email="f9@x.com", nome="Fernanda", sobrenome="Lima", tag="0099", senha_hash="x")
    db.session.add(f); db.session.flush()
    db.session.add(Amizade(solicitante_id=me.id, destinatario_id=f.id, status="aceito")); db.session.commit()
    assert b"Fernanda" in client.get(f"/perfil/{me.username}").data
    f.mostrar_amigos = True; db.session.commit()
    outro = Usuario(username="curioso", email="c@x.com", nome="Curioso", sobrenome="X", tag="0098", senha_hash="x", mostrar_amigos=False)
    db.session.add(outro); db.session.flush()
    db.session.add(Amizade(solicitante_id=outro.id, destinatario_id=f.id, status="aceito")); db.session.commit()
    assert b"id=\"h-am\"" not in client.get("/perfil/curioso").data
    outro.mostrar_amigos = True; db.session.commit()
    assert b"Fernanda" in client.get("/perfil/curioso").data


def test_exclusao_repassa_administracao_do_grupo_e_apaga_grupo_vazio(app):
    from app.models import GrupoChat, GrupoMembro
    a, b, c = [Usuario(username=f"g{i}", email=f"g{i}@x.com", nome=f"G{i}", sobrenome="X", tag=f"01{i}0", senha_hash="x") for i in range(3)]
    db.session.add_all([a, b, c]); db.session.flush()
    g1 = GrupoChat(nome="Duplas", criador_id=a.id); g2 = GrupoChat(nome="Solo", criador_id=a.id); db.session.add_all([g1, g2]); db.session.flush()
    db.session.add_all([GrupoMembro(grupo_id=g1.id, usuario_id=a.id, eh_admin=True), GrupoMembro(grupo_id=g1.id, usuario_id=b.id),
                        GrupoMembro(grupo_id=g1.id, usuario_id=c.id), GrupoMembro(grupo_id=g2.id, usuario_id=a.id, eh_admin=True)])
    db.session.commit()
    from app.services import conta
    conta.excluir(a); db.session.commit()
    assert GrupoMembro.query.filter_by(grupo_id=g1.id, eh_admin=True).count() == 1
    assert db.session.get(GrupoChat, g2.id) is None


def test_exportacao_inclui_simulados_missoes_competicoes_e_registro_e_exclusao_anonimiza_ip(client):
    from app.models import LogAuditoria
    from app.services import conta
    registrar(client)
    u = Usuario.query.filter_by(email=DADOS["email"].lower()).one()
    db.session.add(LogAuditoria(usuario_id=u.id, acao="login", ip="203.0.113.7", user_agent="UA")); db.session.commit()
    d = conta.exportar(u)
    for k in ("sequencia", "simulados", "revisao", "missoes", "competicoes", "amigos", "bloqueados", "registro_de_seguranca"):
        assert k in d
    assert any(l["ip"] == "203.0.113.7" for l in d["registro_de_seguranca"])
    conta.excluir(u); db.session.commit()
    assert all(l.ip is None and l.user_agent is None for l in LogAuditoria.query.filter_by(usuario_id=u.id))


def test_exclusao_apos_renomear_ainda_anonimiza_avisos_de_outros(app):
    from app.models import Notificacao
    from app.services import conta, notificacoes
    a = Usuario(username="r1", email="r1@x.com", nome="Maria", sobrenome="S", tag="0711", senha_hash="x")
    b = Usuario(username="r2", email="r2@x.com", nome="Caio", sobrenome="S", tag="0712", senha_hash="x")
    db.session.add_all([a, b]); db.session.flush()
    notificacoes.criar(b.id, "amizade", "Novo pedido de amizade", "Maria quer ser seu amigo.", "/amigos", origem_id=a.id)
    a.nome = "Ana"; db.session.commit()  # renomeou antes de excluir
    conta.excluir(a); db.session.commit()
    assert "Maria" not in Notificacao.query.filter_by(usuario_id=b.id).one().corpo


def test_pagamento_aprovado_depois_da_exclusao_nao_entrega_nada(client, app):
    from app.models import Pagamento
    from app.services import conta, pagamentos
    from app.providers.base import Notificacao as N
    from tests.test_auth import registrar as reg
    reg(client)
    u = Usuario.query.one()
    pg = Pagamento(usuario_id=u.id, tipo="moedas", produto_ref="starter", provider="stripe", status="criado", valor_centavos=1190, moedas_total=200,
                   chave_idempotencia="kx", descricao="t", provider_ref="cs_9", criado_em=clock.agora() - timedelta(days=3))
    db.session.add(pg); db.session.commit()
    conta.excluir(u); db.session.commit()
    n = N(pagamento_id=str(pg.id), provider_payment_id="pi_9", provider_ref="cs_9", status="aprovado", valor_centavos=1190, moeda="BRL", tipo="x", evento_id="e9")
    assert pagamentos.aplicar(n, "stripe") == "conta_excluida"
    db.session.refresh(u); db.session.refresh(pg)
    assert u.moedas == 0 and pg.status == "divergente"


def test_conta_sem_senha_exige_login_recente_para_excluir(client):
    import time
    registrar(client)
    u = Usuario.query.filter_by(email=DADOS["email"]).one()
    u.senha_hash = None; db.session.commit()  # conta que entra só com Google
    with client.session_transaction() as s:
        s["login_ts"] = int(time.time()) - 3600
    client.post("/configuracoes/excluir-conta", data={"confirmacao": "EXCLUIR"})
    assert Usuario.query.get(u.id).email == DADOS["email"]  # login antigo: nada foi excluído
    with client.session_transaction() as s:
        s["login_ts"] = int(time.time())
    client.post("/configuracoes/excluir-conta", data={"confirmacao": "EXCLUIR"})
    assert Usuario.query.get(u.id).email != DADOS["email"]
