from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError

from app.models import Usuario
from app.security import limpar_texto, validar_senha, validar_username


class FormRegistro(FlaskForm):
    nome = StringField("Nome", validators=[DataRequired(message="Informe seu nome."), Length(2, 80)])
    sobrenome = StringField("Sobrenome", validators=[DataRequired(message="Informe seu sobrenome."), Length(2, 80)])
    username = StringField("Nome de usuário", validators=[DataRequired(message="Escolha um nome de usuário.")])
    email = StringField("E-mail", validators=[DataRequired(message="Informe seu e-mail."), Email(message="E-mail inválido."), Length(max=120)])
    senha = PasswordField("Senha", validators=[DataRequired(message="Crie uma senha.")])
    confirmar_senha = PasswordField("Confirmar senha", validators=[DataRequired(message="Repita a senha."), EqualTo("senha", message="As senhas não coincidem.")])
    aceito = BooleanField("Li e aceito os termos de uso", validators=[DataRequired(message="É preciso aceitar os termos para criar a conta.")])

    def validate_nome(self, f):
        f.data = limpar_texto(f.data, 80)

    def validate_sobrenome(self, f):
        f.data = limpar_texto(f.data, 80)

    def validate_username(self, f):
        f.data = (f.data or "").strip().lower()
        ok, msg = validar_username(f.data)
        if not ok:
            raise ValidationError(msg)
        if Usuario.query.filter_by(username=f.data).first():
            raise ValidationError("Este nome de usuário já está em uso.")

    def validate_email(self, f):
        f.data = (f.data or "").strip().lower()
        if Usuario.query.filter_by(email=f.data).first():
            raise ValidationError("Este e-mail já está cadastrado. Tente entrar ou recuperar a senha.")

    def validate_senha(self, f):
        ok, msg = validar_senha(f.data or "", email=(self.email.data or ""), username=(self.username.data or ""))
        if not ok:
            raise ValidationError(msg)


class FormLogin(FlaskForm):
    email = StringField("E-mail", validators=[DataRequired(message="Informe seu e-mail."), Length(max=120)])
    senha = PasswordField("Senha", validators=[DataRequired(message="Informe sua senha.")])
    lembrar = BooleanField("Manter conectado neste dispositivo")


class FormRecuperarSenha(FlaskForm):
    email = StringField("E-mail", validators=[DataRequired(message="Informe seu e-mail."), Email(message="E-mail inválido."), Length(max=120)])


class FormRedefinirSenha(FlaskForm):
    nova_senha = PasswordField("Nova senha", validators=[DataRequired(message="Crie a nova senha.")])
    confirmar_senha = PasswordField("Confirmar nova senha", validators=[DataRequired(message="Repita a senha."), EqualTo("nova_senha", message="As senhas não coincidem.")])

    def validate_nova_senha(self, f):
        ok, msg = validar_senha(f.data or "")
        if not ok:
            raise ValidationError(msg)
