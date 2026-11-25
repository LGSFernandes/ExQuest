import re

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import BooleanField, PasswordField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, EqualTo, Length, Optional, ValidationError

from app.security import limpar_texto, validar_senha

HEX = re.compile(r"#[0-9a-fA-F]{6}")
FONTES = (("", "Padrão"), ("serif", "Serifada"), ("mono", "Monoespaçada"), ("redonda", "Arredondada"), ("condensada", "Condensada"))
IMG = FileAllowed(["png", "jpg", "jpeg", "webp", "gif"], "Use PNG, JPG, WebP ou GIF.")


class FormPerfil(FlaskForm):
    nome = StringField("Nome", validators=[DataRequired(), Length(2, 80)])
    sobrenome = StringField("Sobrenome", validators=[DataRequired(), Length(2, 80)])
    biografia = TextAreaField("Biografia", validators=[Length(max=300)])
    icon_file = FileField("Foto de perfil", validators=[IMG])
    remover_icon = BooleanField("Remover foto")
    banner_file = FileField("Banner", validators=[IMG])
    remover_banner = BooleanField("Remover banner")
    mostrar_stats = BooleanField("Mostrar minhas estatísticas")
    mostrar_historico = BooleanField("Mostrar minhas últimas respostas")
    mostrar_amigos = BooleanField("Mostrar meus amigos")
    bloquear_pedidos_amizade = BooleanField("Não receber pedidos de amizade")
    nick_cor = StringField("Cor do nome", validators=[Optional()])
    nick_cor2 = StringField("Segunda cor (gradiente)", validators=[Optional()])
    nick_fonte = SelectField("Fonte do nome", choices=FONTES, validate_choice=False)  # o select vem desabilitado sem plano; a permissão é conferida na rota
    tag_custom = StringField("Tag personalizada", validators=[Optional(), Length(max=10)])

    def validate_nome(self, f):
        f.data = limpar_texto(f.data, 80)

    def validate_sobrenome(self, f):
        f.data = limpar_texto(f.data, 80)

    def validate_biografia(self, f):
        f.data = limpar_texto(f.data, 300, multilinha=True)

    def validate_nick_cor(self, f):
        if f.data and not HEX.fullmatch(f.data):
            raise ValidationError("Use uma cor no formato #RRGGBB.")

    validate_nick_cor2 = validate_nick_cor

    def validate_tag_custom(self, f):
        if f.data and not re.fullmatch(r"[A-Za-z0-9_]{2,10}", f.data.strip()):
            raise ValidationError("A tag aceita 2 a 10 letras, números ou _.")


class FormSenha(FlaskForm):
    senha_atual = PasswordField("Senha atual", validators=[DataRequired()])
    nova_senha = PasswordField("Nova senha", validators=[DataRequired()])
    confirmar = PasswordField("Repita a nova senha", validators=[DataRequired(), EqualTo("nova_senha", message="As senhas não coincidem.")])
