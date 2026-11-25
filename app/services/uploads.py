"""Upload de imagens. Valida o CONTEÚDO (Pillow), não a extensão nem o Content-Type enviados pelo cliente.

- formatos: PNG, JPEG, WebP e GIF (GIF só quando o plano permite); nome novo aleatório com extensão do formato detectado;
- limites de bytes, de dimensões e de quadros (proteção contra decompression bomb);
- imagens estáticas são regravadas em WebP (remove EXIF/GPS e metadados, reduz o peso) e reduzidas ao tamanho máximo de exibição;
  GIF animado é validado e gravado como veio;
- públicos em UPLOAD_ROOT/<pasta> (servidos em /static/data/<pasta>); privados em instance/private/<pasta> (chat)."""
import io
import os
import secrets
from pathlib import Path

from flask import current_app
from sqlalchemy import event

from app.extensions import db
from PIL import Image, ImageOps, UnidentifiedImageError

Image.MAX_IMAGE_PIXELS = 40_000_000

_EXT = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp", "GIF": ".gif"}
MAX_BYTES = {"icon": 2 * 1024 * 1024, "banner": 5 * 1024 * 1024, "img_questao": 3 * 1024 * 1024, "chat": 4 * 1024 * 1024}
MAX_LADO = {"icon": 1024, "banner": 3000, "img_questao": 2400, "chat": 3000}
ARMAZENA_LADO = {"icon": 256, "banner": 1600, "img_questao": 1600, "chat": 1600}  # maior lado gravado (a entrada aceita é maior)
WEBP_QUALIDADE = 82
MAX_QUADROS = 300
MAX_PIXELS_GIF = 120_000_000  # quadros x largura x altura


class UploadInvalido(ValueError):
    """Mensagem em português, segura para mostrar ao usuário."""


def _raiz(privado: bool) -> Path:
    if privado:
        return Path(current_app.instance_path) / "private"
    return Path(current_app.config["UPLOAD_ROOT"])


def salvar_imagem(arquivo, pasta: str, *, permitir_gif: bool, privado: bool = False, prefixo: str = "") -> str:
    """Retorna o nome do arquivo gravado. Levanta UploadInvalido com motivo legível."""
    if pasta not in MAX_BYTES:
        raise ValueError(f"pasta de upload desconhecida: {pasta}")
    if arquivo is None or not getattr(arquivo, "filename", ""):
        raise UploadInvalido("Nenhum arquivo enviado.")
    dados = arquivo.read(MAX_BYTES[pasta] + 1)
    if not dados:
        raise UploadInvalido("O arquivo está vazio.")
    if len(dados) > MAX_BYTES[pasta]:
        raise UploadInvalido(f"O arquivo excede {MAX_BYTES[pasta] // (1024 * 1024)} MB.")
    try:
        img = Image.open(io.BytesIO(dados))
        formato = img.format
        img.verify()  # verify invalida o objeto: reabrimos para ler pixels
        img = Image.open(io.BytesIO(dados))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError):
        raise UploadInvalido("O arquivo não é uma imagem válida (use PNG, JPG, WebP ou GIF).")
    if formato not in _EXT:
        raise UploadInvalido("Formato não aceito. Use PNG, JPG, WebP ou GIF.")
    if max(img.size) > MAX_LADO[pasta]:
        raise UploadInvalido(f"A imagem é grande demais (máximo {MAX_LADO[pasta]} px de lado).")
    if formato == "GIF":
        if not permitir_gif:  # antes de qualquer varredura de quadros: o plano barra sem custo de CPU
            raise UploadInvalido("GIFs estão disponíveis a partir do plano Básico.")
        quadros = 0
        limite = min(MAX_QUADROS, MAX_PIXELS_GIF // max(1, img.size[0] * img.size[1]))  # o orçamento de pixels limita a varredura ANTES de decodificar
        try:
            while quadros <= limite:  # varredura com parada antecipada (n_frames decodificaria todos)
                img.seek(quadros)
                quadros += 1
        except EOFError:
            pass
        if quadros > limite:
            raise UploadInvalido("O GIF tem quadros demais ou é pesado demais.")
        saida = dados
    elif getattr(img, "is_animated", False):  # WebP/PNG animados não são aceitos: só GIF animado
        raise UploadInvalido("Imagens animadas só são aceitas em GIF.")
    else:
        buf = io.BytesIO()
        img = ImageOps.exif_transpose(img)  # a orientação do EXIF vira pixels antes de o EXIF ser descartado (foto de celular não gira)
        img.thumbnail((ARMAZENA_LADO[pasta],) * 2, Image.LANCZOS)  # só reduz; nunca amplia
        tem_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
        img = img.convert("RGBA" if tem_alpha else "RGB")
        img.save(buf, format="WEBP", quality=WEBP_QUALIDADE, method=4)
        saida, formato = buf.getvalue(), "WEBP"
    nome = f"{prefixo}{secrets.token_hex(8)}{_EXT[formato]}"
    destino = _raiz(privado) / pasta
    destino.mkdir(parents=True, exist_ok=True)
    (destino / nome).write_bytes(saida)
    return nome


def remover(pasta: str, nome: str | None, *, privado: bool = False) -> None:
    """Apaga um upload anterior. Só aceita nome simples dentro da pasta (sem barras/..)."""
    if not nome or nome != os.path.basename(nome) or pasta not in MAX_BYTES:
        return
    try:
        (_raiz(privado) / pasta / nome).unlink(missing_ok=True)
    except OSError:
        current_app.logger.warning("não foi possível remover upload %s/%s", pasta, nome)


def remover_apos_commit(pasta: str, nome: str | None, *, privado: bool = False) -> None:
    """Apaga o arquivo só se o commit da transação atual der certo (rollback cancela: nunca fica linha sem arquivo)."""
    if not nome:
        return
    sess = db.session()

    def _soltar():
        for ev, fn in (("after_commit", _depois), ("after_rollback", _cancela)):
            if event.contains(sess, ev, fn):
                event.remove(sess, ev, fn)

    def _depois(_s):
        _soltar()
        remover(pasta, nome, privado=privado)

    def _cancela(_s):
        _soltar()
    event.listen(sess, "after_commit", _depois)
    event.listen(sess, "after_rollback", _cancela)


def caminho(pasta: str, nome: str, *, privado: bool = False) -> Path | None:
    """Caminho seguro de um upload existente (para servir via rota autorizada)."""
    if not nome or nome != os.path.basename(nome) or pasta not in MAX_BYTES:
        return None
    p = _raiz(privado) / pasta / nome
    return p if p.is_file() else None


def reotimizar(pasta: str, nome: str, *, privado: bool = False) -> str | None:
    """Converte um upload antigo (PNG/JPEG) para WebP reduzido. Devolve o novo nome, ou None se não valer a pena
    (já é WebP/GIF, arquivo ausente/inválido ou o resultado não ficou menor). Não apaga o original: quem chama faz isso depois do commit."""
    origem = caminho(pasta, nome, privado=privado)
    if origem is None or nome.lower().endswith((".webp", ".gif")):
        return None
    try:
        bruto = Path(origem).read_bytes()
        img = Image.open(io.BytesIO(bruto))
        if img.format not in ("PNG", "JPEG") or getattr(img, "is_animated", False):
            return None
        img = ImageOps.exif_transpose(img)
        img.thumbnail((ARMAZENA_LADO[pasta],) * 2, Image.LANCZOS)
        tem_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
        buf = io.BytesIO()
        img.convert("RGBA" if tem_alpha else "RGB").save(buf, format="WEBP", quality=WEBP_QUALIDADE, method=4)
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError):
        return None
    if len(buf.getvalue()) >= len(bruto):
        return None
    novo = f"{Path(nome).stem}{secrets.token_hex(2)}.webp"
    (Path(origem).parent / novo).write_bytes(buf.getvalue())
    return novo
