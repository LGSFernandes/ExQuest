import re
from pathlib import Path

from flask import current_app
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import BooleanField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional, Regexp, ValidationError


class FormQuestao(FlaskForm):
    materia_id = SelectField("Matéria", coerce=int, validators=[DataRequired()])
    dificuldade = SelectField("Dificuldade", choices=[("facil", "Fácil"), ("medio", "Média"), ("dificil", "Difícil")])
    tipo = SelectField("Tipo", choices=[("multipla", "Múltipla escolha"), ("discursiva", "Discursiva")])
    conteudo = StringField("Assunto", validators=[Optional(), Length(max=100)])
    enunciado = TextAreaField("Enunciado", validators=[DataRequired(), Length(max=5000)])
    explicacao = TextAreaField("Explicação", validators=[Optional(), Length(max=5000)])
    resposta_correta = TextAreaField("Gabarito da discursiva", validators=[Optional(), Length(max=5000)])
    imagem = FileField("Imagem", validators=[FileAllowed(["png", "jpg", "jpeg", "webp"], "Use PNG, JPG ou WebP.")])
    remover_imagem = BooleanField("Remover imagem")
    ativo = BooleanField("Disponível para os alunos", default=True)


def icones_disponiveis() -> list[str]:
    """Ids do sprite SVG: a lista nunca fica fora de sincronia com os ícones que existem."""
    svg = Path(current_app.static_folder, "icons.svg").read_text(encoding="utf-8")
    return sorted(set(re.findall(r'<symbol id="([a-z0-9-]+)"', svg)))


class FormMateria(FlaskForm):
    nome = StringField("Nome", validators=[DataRequired(), Length(min=2, max=100)])
    icone_chave = SelectField("Ícone", validators=[DataRequired()])
    cor = StringField("Cor", validators=[DataRequired(), Regexp(r"^#[0-9a-fA-F]{6}$", message="Use o formato #RRGGBB.")],
                      default="#2f4fb8")
    ativo = BooleanField("Disponível para os alunos", default=True)

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.icone_chave.choices = [(i, i) for i in icones_disponiveis()]

    def validate_icone_chave(self, campo):
        if campo.data not in dict(self.icone_chave.choices):
            raise ValidationError("Ícone inexistente.")
