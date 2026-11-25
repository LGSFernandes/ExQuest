"""Migrations: banco vazio, banco legado (esquema 1.6 com dados) e ausência de drift contra os modelos."""
import sqlite3

import pytest
from flask_migrate import check, upgrade

from app import create_app

LEGADO = "62e588f5787b"  # última revisão do ExQuest original


def _app(tmp_path):
    return create_app("testing", {"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 't.db'}"})


def test_banco_vazio_chega_ao_head_sem_drift(tmp_path):
    app = _app(tmp_path)
    with app.app_context():
        upgrade()
        check()  # levanta se os modelos divergirem das migrations


def test_banco_legado_preserva_dados_e_faz_backfill(tmp_path):
    app = _app(tmp_path)
    arq = tmp_path / "t.db"
    with app.app_context():
        upgrade(revision=LEGADO)
    con = sqlite3.connect(arq)
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("INSERT INTO usuarios (id,nome,sobrenome,username,email,tag,xp,moedas,plano_premium) "
                "VALUES (1,'Ana','Silva','ana','ana@x.com','AAAA',670,121,'free')")
    con.execute("INSERT INTO usuarios (id,nome,sobrenome,username,email,tag,xp,moedas) VALUES (2,'Bia','L','bia','b@x.com','BBBB',0,0)")
    con.execute("INSERT INTO materias (id,nome,icone) VALUES (1,'História','🕸')")
    con.execute("INSERT INTO itens_loja (id,nome,descricao,tipo,preco,css_class) VALUES (1,'Borda Prata','d','borda',80,'border-prata')")
    con.execute("INSERT INTO itens_loja (id,nome,descricao,tipo,preco) VALUES (2,'Boost XP 50% (24h)','d','boost_xp',120)")
    con.commit(); con.close()

    with app.app_context():
        upgrade()
        check()
    con = sqlite3.connect(arq)
    q = lambda s: con.execute(s).fetchall()
    assert q("select xp, moedas from usuarios where id=1") == [(670, 121)]  # dados originais intactos
    assert q("select valor, saldo_apos, categoria from carteira_lancamentos") == [(121, 121, "saldo_inicial")]
    assert q("select valor from xp_eventos") == [(670,)]
    assert q("select slug from itens_loja order by id") == [("border-prata",), ("boost-xp-50-24h",)]
    assert q("select icone, icone_chave from materias") == [("🕸", "landmark")]
    assert q("select perfil_publico, session_version, questoes_bonus from usuarios where id=2") == [(0, 0, 0)]
    assert q("pragma foreign_key_check") == []


def test_duplicados_abortam_sem_alterar_o_banco(tmp_path, caplog):
    app = _app(tmp_path)
    arq = tmp_path / "t.db"
    with app.app_context():
        upgrade(revision=LEGADO)
    con = sqlite3.connect(arq)
    con.execute("INSERT INTO usuarios (id,nome,sobrenome,username,email,tag) VALUES (1,'A','B','a','a@x.com','AAAA')")
    con.execute("INSERT INTO streaks (usuario_id) VALUES (1)")
    con.execute("INSERT INTO streaks (usuario_id) VALUES (1)")  # duplicado: impediria o índice único
    con.commit(); con.close()
    with app.app_context(), pytest.raises(SystemExit):  # Flask-Migrate converte o erro em SystemExit(1)
        upgrade()
    assert "duplicados" in caplog.text and "streaks(usuario_id)" in caplog.text
    con = sqlite3.connect(arq)
    assert con.execute("select version_num from alembic_version").fetchall() == [(LEGADO,)]
    assert con.execute("select count(*) from sqlite_master where name='carteira_lancamentos'").fetchone() == (0,)
