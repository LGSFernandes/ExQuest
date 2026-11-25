import io

import pytest
from PIL import Image
from werkzeug.datastructures import FileStorage

from app.security import limpar_texto, url_interna_segura, validar_senha, validar_username
from app.services import uploads


def _arq(conteudo: bytes, nome="x.png"):
    return FileStorage(stream=io.BytesIO(conteudo), filename=nome)


def _png(tam=(20, 20), exif=False):
    b = io.BytesIO()
    im = Image.new("RGB", tam, (200, 10, 10))
    if exif:
        ex = Image.Exif(); ex[0x010F] = "CameraMarca"; im.save(b, "JPEG", exif=ex)
    else:
        im.save(b, "PNG")
    return b.getvalue()


def _gif(n=3):
    b = io.BytesIO()
    quadros = [Image.new("P", (10, 10), 0) for _ in range(n)]
    for i, q in enumerate(quadros):  # quadros distintos: o Pillow funde quadros idênticos ao gravar
        q.putpixel((i % 10, i // 10 % 10), 1 + i % 200)
    quadros[0].save(b, "GIF", save_all=True, append_images=quadros[1:], duration=50)
    return b.getvalue()


@pytest.fixture()
def pasta_upload(app, tmp_path):
    app.config["UPLOAD_ROOT"] = str(tmp_path / "up")
    app.instance_path = str(tmp_path / "inst")
    return tmp_path


def test_png_valido_e_renomeado(app, pasta_upload):
    nome = uploads.salvar_imagem(_arq(_png(), "../../etc/passwd.png"), "icon", permitir_gif=False)
    assert nome.endswith(".webp") and "/" not in nome and ".." not in nome
    assert (pasta_upload / "up" / "icon" / nome).is_file()


def test_arquivo_falso_com_extensao_de_imagem_e_recusado(app, pasta_upload):
    with pytest.raises(uploads.UploadInvalido):
        uploads.salvar_imagem(_arq(b"<script>alert(1)</script>", "foto.png"), "icon", permitir_gif=False)
    with pytest.raises(uploads.UploadInvalido):
        uploads.salvar_imagem(_arq(b"<svg onload=alert(1)></svg>", "foto.svg"), "icon", permitir_gif=False)


def test_exif_e_removido(app, pasta_upload):
    nome = uploads.salvar_imagem(_arq(_png(exif=True), "f.jpg"), "icon", permitir_gif=False)
    salvo = Image.open(pasta_upload / "up" / "icon" / nome)
    assert not salvo.getexif()


def test_gif_exige_plano_e_tamanho_e_dimensao_sao_limitados(app, pasta_upload):
    with pytest.raises(uploads.UploadInvalido, match="Básico"):
        uploads.salvar_imagem(_arq(_gif(), "a.gif"), "banner", permitir_gif=False)
    assert uploads.salvar_imagem(_arq(_gif(), "a.gif"), "banner", permitir_gif=True).endswith(".gif")
    with pytest.raises(uploads.UploadInvalido, match="grande demais"):
        uploads.salvar_imagem(_arq(_png((1100, 10)), "a.png"), "icon", permitir_gif=False)
    with pytest.raises(uploads.UploadInvalido, match="MB"):
        uploads.salvar_imagem(_arq(b"0" * (2 * 1024 * 1024 + 5), "a.png"), "icon", permitir_gif=False)


def test_remover_nao_sai_da_pasta(app, pasta_upload):
    alvo = pasta_upload / "segredo.txt"
    alvo.write_text("x")
    uploads.remover("icon", "../segredo.txt")
    assert alvo.exists()


def test_privado_vai_para_instance(app, pasta_upload):
    nome = uploads.salvar_imagem(_arq(_png(), "a.png"), "chat", permitir_gif=False, privado=True)
    assert (pasta_upload / "inst" / "private" / "chat" / nome).is_file()
    assert uploads.caminho("chat", nome, privado=True) is not None and uploads.caminho("chat", "../x", privado=True) is None


def test_url_interna_segura(app):
    with app.test_request_context("/", base_url="http://exquest.test"):
        assert url_interna_segura("/loja?x=1") == "/loja?x=1"
        for ruim in ("//evil.com", "https://evil.com/x", "/\\evil.com", "javascript:alert(1)", ""):
            assert url_interna_segura(ruim) == "/", ruim


def test_validacoes_de_cadastro():
    assert validar_username("ana.silva_2")[0] and not validar_username("Ana Silva")[0] and not validar_username("admin")[0]
    assert not validar_username("<script>")[0]
    assert not validar_senha("1234567")[0] and not validar_senha("password")[0] and not validar_senha("aaaaaaaaaa")[0]
    assert not validar_senha("joaosilva1", email="joaosilva1@x.com")[0]  # igual à parte local do e-mail
    assert validar_senha("cavalo-bateria-9")[0]


def test_limpar_texto_preserva_matematica_e_remove_controle():
    assert limpar_texto("x -- y; z /* w */") == "x -- y; z /* w */"
    assert limpar_texto("oi‮tchau\x00") == "oitchau"
    assert limpar_texto("a\nb") == "a b" and limpar_texto("a\nb", multilinha=True) == "a\nb"


def test_gif_com_quadros_demais_e_recusado_e_plano_barra_antes_da_varredura(app, pasta_upload):
    with pytest.raises(uploads.UploadInvalido, match="quadros demais"):
        uploads.salvar_imagem(_arq(_gif(uploads.MAX_QUADROS + 5), "a.gif"), "banner", permitir_gif=True)
    with pytest.raises(uploads.UploadInvalido, match="Básico"):
        uploads.salvar_imagem(_arq(_gif(uploads.MAX_QUADROS + 5), "a.gif"), "banner", permitir_gif=False)
    assert uploads.salvar_imagem(_arq(_gif(uploads.MAX_QUADROS), "a.gif"), "banner", permitir_gif=True).endswith(".gif")


def test_gif_grande_e_recusado_pelo_orcamento_de_pixels_antes_de_decodificar_todos_os_quadros(app, pasta_upload, monkeypatch):
    """Achado hunter-09: o orçamento de pixels era checado só depois de varrer até 301 quadros grandes."""
    from PIL import Image
    visitados = []
    orig = Image.Image.seek
    monkeypatch.setattr(Image.Image, "seek", lambda self, n: (visitados.append(n), orig(self, n))[1])
    monkeypatch.setattr(uploads, "MAX_PIXELS_GIF", 10 * 10 * 4)  # orçamento: 4 quadros de 10x10
    with pytest.raises(uploads.UploadInvalido, match="pesado demais"):
        uploads.salvar_imagem(_arq(_gif(30), "a.gif"), "banner", permitir_gif=True)
    assert max(visitados) <= 6, visitados  # parou perto do limite em vez de varrer os 30 quadros
