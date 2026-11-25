"""LaTeX (KaTeX local) em todas as telas e editor de questões do admin."""
import re

from app.extensions import db
from app.models import Alternativa, Materia, Questao, RespostaUsuario, Usuario
from tests.test_auth import DADOS, registrar


def _admin(client, admin=True):
    registrar(client)
    u = Usuario.query.filter_by(email=DADOS["email"]).one()
    u.is_admin = admin
    db.session.commit()
    return u


def test_katex_carregado_no_layout_e_arquivos_servidos(client):
    _admin(client)
    html = client.get("/").data.decode()
    assert not re.findall(r'<(?:script src|link[^>]+href)="/static/vendor/katex', html)  # o KaTeX não é baixado em toda página: só sob demanda
    srcs = re.findall(r'(?:src|data-css|data-js|data-auto)="(/static/(?:vendor/katex|js/katex-init)[^"]+)"', html)
    assert len(srcs) == 4, srcs  # o carregador + as 3 URLs versionadas que ele usa quando há fórmula
    for s in srcs:
        assert client.get(s).status_code == 200, s
    css = client.get("/static/vendor/katex/katex.min.css").data.decode()
    for f in set(re.findall(r"url\(([^)]+\.woff2)\)", css)):  # fontes referenciadas pelo CSS existem
        assert client.get("/static/vendor/katex/" + f.strip("'\"")).status_code == 200, f
    assert "script-src 'self'" in client.get("/").headers["Content-Security-Policy"]


def test_admin_exige_permissao(client):
    _admin(client, admin=False)
    for url in ("/admin/", "/admin/questoes", "/admin/questoes/nova", "/admin/materias", "/admin/materias/nova", "/admin/questoes/importar", "/admin/questoes/exportar"):
        assert client.get(url).status_code == 403
    assert client.post("/admin/questoes/nova", data={}).status_code in (400, 403)


def test_admin_cria_edita_questao_com_latex_sem_apagar_alternativa_respondida(client):
    u = _admin(client)
    m = Materia(nome="Mat"); db.session.add(m); db.session.commit()
    base = dict(materia_id=m.id, dificuldade="facil", tipo="multipla", conteudo="", enunciado=r"Calcule $\frac{1}{2}$",
                explicacao=r"$$x^2$$", alt_texto=[r"$\sqrt{2}$", "b", "c", ""], alt_correta="1", ativo="y")
    r = client.post("/admin/questoes/nova", data=base)
    assert r.status_code == 302
    q = Questao.query.one()
    assert q.enunciado == r"Calcule $\frac{1}{2}$" and [a.texto for a in q.alternativas] == [r"$\sqrt{2}$", "b", "c"]
    assert [a.correta for a in q.alternativas] == [False, True, False]
    assert r"\frac{1}{2}" in client.get(f"/admin/questoes/{q.id}/editar").data.decode()  # escapado pelo Jinja, sem perder a barra
    # aluno respondeu a alternativa 3: remover essa alternativa é recusado
    db.session.add(RespostaUsuario(usuario_id=u.id, questao_id=q.id, alternativa_id=q.alternativas[2].id, acertou=False, modo="pratica"))
    db.session.commit()
    r = client.post(f"/admin/questoes/{q.id}/editar", data={**base, "alt_texto": ["x", "y"], "alt_correta": "0"})
    assert r.status_code == 200 and "já foi escolhida" in r.data.decode()
    assert Alternativa.query.count() == 3
    # editar o texto mantendo a quantidade funciona
    r = client.post(f"/admin/questoes/{q.id}/editar", data={**base, "alt_texto": ["x", "y", "z"], "alt_correta": "2"})
    assert r.status_code == 302 and [a.texto for a in Questao.query.one().alternativas] == ["x", "y", "z"]


def test_multipla_exige_uma_correta(client):
    _admin(client)
    m = Materia(nome="Mat"); db.session.add(m); db.session.commit()
    r = client.post("/admin/questoes/nova", data=dict(materia_id=m.id, dificuldade="facil", tipo="multipla", enunciado="x",
                                                      alt_texto=["a", "b"], ativo="y"))
    assert r.status_code == 200 and Questao.query.count() == 0


def test_materias_crud_e_validacoes(client):
    _admin(client)
    assert client.get("/admin/materias").status_code == 200
    r = client.post("/admin/materias/nova", data={"nome": "Física", "icone_chave": "atom", "cor": "#112233", "ativo": "y"})
    assert r.status_code == 302
    m = Materia.query.one()
    assert (m.nome, m.icone_chave, m.cor) == ("Física", "atom", "#112233")
    for ruim in ({"nome": "física", "icone_chave": "atom", "cor": "#112233"},           # nome duplicado (sem diferenciar caixa)
                 {"nome": "X1", "icone_chave": "nao-existe", "cor": "#112233"},          # ícone fora do sprite
                 {"nome": "X2", "icone_chave": "atom", "cor": "red;background:url(x)"}):  # cor inválida
        assert client.post("/admin/materias/nova", data=ruim).status_code == 200
    assert Materia.query.count() == 1
    assert client.post(f"/admin/materias/{m.id}/editar", data={"nome": "Física", "icone_chave": "atom", "cor": "#445566"}).status_code == 302
    assert Materia.query.one().ativo is False  # checkbox desmarcado


def test_exportar_e_importar_questoes_tudo_ou_nada(client):
    import io, json
    _admin(client)
    m = Materia(nome="Mat"); db.session.add(m); db.session.commit()
    ok = {"materia": "mat", "dificuldade": "facil", "tipo": "multipla", "enunciado": r"Quanto é $1+1$?",
          "alternativas": [{"texto": "2", "correta": True}, {"texto": "3", "correta": False}]}
    def enviar(doc, bruto=None):
        corpo = bruto if bruto is not None else json.dumps(doc).encode()
        return client.post("/admin/questoes/importar", data={"arquivo": (io.BytesIO(corpo), "q.json")}, content_type="multipart/form-data")
    assert "1 questões importadas" in enviar({"questoes": [ok]}).data.decode()
    assert "1 já existiam" in enviar({"questoes": [ok]}).data.decode()       # idempotente
    ruim = {**ok, "enunciado": "outro", "alternativas": [{"texto": "a", "correta": True}, {"texto": "b", "correta": True}]}
    r = enviar({"questoes": [{**ok, "enunciado": "novo valido"}, ruim, {**ok, "materia": "inexistente"}]})
    assert r.status_code == 422 and "2 problema" in r.data.decode() and Questao.query.count() == 1  # nada entrou
    assert enviar(None, bruto=b"{nao json").status_code == 400
    assert enviar(None, bruto=b"x" * (2 * 1024 * 1024 + 5)).status_code == 400
    exp = client.get("/admin/questoes/exportar")
    assert exp.headers["Content-Disposition"].startswith("attachment") and json.loads(exp.data)["questoes"][0]["materia"] == "Mat"
    assert client.get("/admin/questoes/exportar").status_code == 200


def test_denuncia_de_perfil_e_moderacao(client):
    from app.models import Denuncia
    adm = _admin(client)
    outro = Usuario(username="outro", email="o@x.com", nome="O", sobrenome="X", tag="0001", senha_hash="x")
    db.session.add(outro); db.session.commit()
    assert client.post("/perfil/outro/denunciar", data={"motivo": "invalido"}).status_code == 302
    assert client.post(f"/perfil/{adm.username}/denunciar", data={"motivo": "spam"}).status_code == 302  # a si mesmo
    assert Denuncia.query.count() == 0
    for _ in range(2):  # repetir não duplica
        client.post("/perfil/outro/denunciar", data={"motivo": "spam"})
    assert Denuncia.query.count() == 1
    assert "@outro" in client.get("/admin/denuncias").data.decode()
    d = Denuncia.query.one()
    db.session.add(Denuncia(autor_id=outro.id, alvo_tipo="usuario", alvo_id=adm.id, motivo="spam")); db.session.commit()
    d_adm = Denuncia.query.filter_by(alvo_id=adm.id).one()
    client.post(f"/admin/denuncias/{d_adm.id}/resolver", data={"acao": "banir"})  # admin não é banível por aqui
    assert Usuario.query.get(adm.id).is_banido is False
    assert client.post(f"/admin/denuncias/{d.id}/resolver", data={"acao": "x"}).status_code == 400
    client.post(f"/admin/denuncias/{d.id}/resolver", data={"acao": "banir"})
    assert Usuario.query.get(outro.id).is_banido is True and Denuncia.query.get(d.id).status == "procedente"
    client.post(f"/admin/denuncias/{d.id}/resolver", data={"acao": "arquivar"})  # já resolvida: não reabre nem muda
    assert Denuncia.query.get(d.id).status == "procedente"


def test_banir_por_denuncia_de_mensagem_apagada_nao_bane_outra_conta(client):
    from app.models import Denuncia
    adm = _admin(client)
    inocente = Usuario(username="inoc", email="i@x.com", nome="I", sobrenome="X", tag="0002", senha_hash="x")
    db.session.add(inocente); db.session.flush()
    d = Denuncia(autor_id=adm.id, alvo_tipo="mensagem", alvo_id=inocente.id, motivo="spam")  # alvo_id é id de mensagem que não existe mais
    db.session.add(d); db.session.commit()
    client.post(f"/admin/denuncias/{d.id}/resolver", data={"acao": "banir"})
    assert Usuario.query.get(inocente.id).is_banido is False and Denuncia.query.get(d.id).status == "aberta"
