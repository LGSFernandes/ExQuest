from datetime import datetime
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (StringField, IntegerField, PasswordField, SubmitField, TextAreaField,
                     SelectField, BooleanField, HiddenField)
from wtforms.validators import DataRequired, Email, Length, EqualTo, Optional, ValidationError, NumberRange
from app.models import Usuario

ALLOWED_IMG = ['png','jpg','jpeg','webp','gif']

# ══════════════════════════════════
#  AUTH
# ══════════════════════════════════

class FormRegistro(FlaskForm):
    nome = StringField('Nome', validators=[DataRequired(), Length(2,80)])
    sobrenome = StringField('Sobrenome', validators=[DataRequired(), Length(2,80)])
    username = StringField('Usuário', validators=[DataRequired(), Length(3,40)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    senha = PasswordField('Senha', validators=[DataRequired(), Length(min=6)])
    confirmar_senha = PasswordField('Confirmar',validators=[DataRequired(), EqualTo('senha', message='Senhas não coincidem.')])
    submit = SubmitField('Criar Conta')

    def validate_username(self, f):
        from app.security import validar_username
        ok, msg = validar_username(f.data)
        if not ok: raise ValidationError(msg)
        if Usuario.query.filter_by(username=f.data.lower()).first():
            raise ValidationError('Username já em uso.')

    def validate_email(self, f):
        if Usuario.query.filter_by(email=f.data.lower()).first():
            raise ValidationError('Email já cadastrado.')

    def validate_nome(self, f):
        from app.security import validar_texto_seguro
        ok, msg = validar_texto_seguro(f.data)
        if not ok: raise ValidationError(msg)


class FormLogin(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    senha = PasswordField('Senha',validators=[DataRequired()])
    lembrar = BooleanField('Lembrar de mim')
    submit = SubmitField('Entrar')


class FormRecuperarSenha(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Enviar instruções')


class FormRedefinirSenha(FlaskForm):
    nova_senha = PasswordField('Nova Senha', validators=[DataRequired(), Length(min=6)])
    confirmar_senha = PasswordField('Confirmar Senha',validators=[DataRequired(), EqualTo('nova_senha', message='Senhas não coincidem.')])
    submit = SubmitField('Redefinir Senha')


# ══════════════════════════════════
#  PERFIL
# ══════════════════════════════════

class FormEditarPerfil(FlaskForm):
    nome = StringField('Nome', validators=[DataRequired(), Length(2,80)])
    sobrenome = StringField('Sobrenome', validators=[DataRequired(), Length(2,80)])
    biografia = TextAreaField('Biografia',validators=[Optional(), Length(max=300)])
    icon_emoji = SelectField('Avatar Emoji', choices=[
        ('avatar_1','\U0001F989 Coruja'),('avatar_2','\U0001F680 Foguete'),('avatar_3','\U00002B50 Estrela'),
        ('avatar_4','\U0001F48E Diamante'),('avatar_5','\U000026A1 Trovão'),('avatar_6','\U0001F525 Chama'),
        ('avatar_7','\U0001F52E Cristal'),('avatar_8','\U0001F6E1\U0000FE0F Escudo'),
    ])
    icon_file = FileField('Foto (upload)', validators=[Optional(), FileAllowed(ALLOWED_IMG)])
    remover_icon = HiddenField(default='')
    banner_file = FileField('Banner (upload)', validators=[Optional(), FileAllowed(ALLOWED_IMG)])
    remover_banner= HiddenField(default='')
    estilo_perfil = SelectField('Estilo Banner', choices=[
        ('padrao','Padrão'),('aurora','Aurora'),('cosmos','Cosmos'),
        ('neon','Neon'),('sunset','Sunset'),('ocean','Ocean'),
    ])
    # Privacidade
    mostrar_stats = BooleanField('Exibir gráficos de desempenho')
    mostrar_historico = BooleanField('Exibir histórico de respostas')
    mostrar_amigos = BooleanField('Exibir lista de amigos')
    bloquear_pedidos_amizade = BooleanField('Não receber pedidos de amizade')
    # Premium: nick
    nick_cor = StringField('Cor do Nick (hex)',      validators=[Optional(), Length(max=20)])
    nick_gradiente = StringField('Gradiente do Nick (CSS)',validators=[Optional(), Length(max=100)])
    nick_fonte = SelectField('Fonte do Nick', choices=[
        ('','Padrão'),('serif','Serif'),('mono','Monospace'),
        ('neon','Neon / Orbitron'),('party','Party / Pacifico'),('elegant','Elegante / Playfair'),
    ], validators=[Optional()])
    tag_custom = StringField('Tag personalizada (#XXXXX)', validators=[Optional(), Length(max=10)])
    submit = SubmitField('Salvar')

    def validate_nome(self, f):
        from app.security import validar_texto_seguro
        ok, msg = validar_texto_seguro(f.data)
        if not ok: raise ValidationError(msg)

    def validate_biografia(self, f):
        if f.data:
            from app.security import validar_texto_seguro
            ok, msg = validar_texto_seguro(f.data)
            if not ok: raise ValidationError(msg)


class FormAlterarSenha(FlaskForm):
    senha_atual = PasswordField('Senha Atual', validators=[DataRequired()])
    nova_senha = PasswordField('Nova Senha', validators=[DataRequired(), Length(min=6)])
    confirmar_senha = PasswordField('Confirmar', validators=[DataRequired(), EqualTo('nova_senha', message='Senhas não coincidem.')])
    submit = SubmitField('Alterar Senha')


# ══════════════════════════════════
#  ADMIN
# ══════════════════════════════════

class FormMateria(FlaskForm):
    nome = StringField('Nome', validators=[DataRequired(), Length(2,100)])
    icone = StringField('Ícone (emoji)', validators=[Optional(), Length(max=10)], default='\U0001F4DA')
    cor = StringField('Cor (hex)', validators=[Optional(), Length(max=20)], default='#6366f1')
    submit = SubmitField('Salvar')


class FormQuestao(FlaskForm):
    enunciado = TextAreaField('Enunciado', validators=[DataRequired(), Length(min=10)])
    explicacao = TextAreaField('Explicação', validators=[Optional()])
    dificuldade = SelectField('Dificuldade', choices=[('facil','Fácil'),('medio','Médio'),('dificil','Difícil')], validators=[DataRequired()])
    materia_id = SelectField('Matéria', coerce=int, validators=[DataRequired()])
    conteudo = StringField('Tópico/Conteúdo', validators=[Optional(), Length(max=100)])
    imagem = FileField('Imagem da Questão', validators=[Optional(), FileAllowed(ALLOWED_IMG)])
    tipo_questao = SelectField('Tipo', choices=[('multipla','Múltipla Escolha'),('discursiva','Discursiva')], default='multipla')
    # Múltipla escolha
    alternativa_a = StringField('Alternativa A', validators=[Optional()])
    alternativa_b = StringField('Alternativa B', validators=[Optional()])
    alternativa_c = StringField('Alternativa C', validators=[Optional()])
    alternativa_d = StringField('Alternativa D', validators=[Optional()])
    correta = SelectField('Correta', choices=[('a','A'),('b','B'),('c','C'),('d','D')], validators=[Optional()])
    # Discursiva
    resposta_correta = TextAreaField('Gabarito (para IA comparar)', validators=[Optional()])
    submit = SubmitField('Salvar Questão')

    def validate_enunciado(self, f):
        from app.security import validar_texto_seguro
        ok, msg = validar_texto_seguro(f.data)
        if not ok: raise ValidationError(msg)


# ══════════════════════════════════
#  SOCIAL
# ══════════════════════════════════

class FormMensagem(FlaskForm):
    conteudo = TextAreaField('Mensagem', validators=[Optional(), Length(max=2000)])
    imagem = FileField('Imagem', validators=[Optional(), FileAllowed(ALLOWED_IMG)])
    submit = SubmitField('Enviar')


class FormGrupo(FlaskForm):
    nome = StringField('Nome do Grupo', validators=[DataRequired(), Length(3,100)])
    icone = StringField('Ícone (emoji)', validators=[Optional(), Length(max=10)], default='\U0001F4AC')
    submit = SubmitField('Criar Grupo')


class FormTorneio(FlaskForm):
    nome = StringField('Nome do Torneio', validators=[DataRequired(), Length(3, 100)])
    descricao = TextAreaField('Descrição', validators=[Optional(), Length(max=500)])
    tipo = SelectField('Tipo', choices=[
        ('pequeno','Pequeno'),('medio','Médio'),('grande','Grande')
    ])
    materia_id = SelectField('Matéria', coerce=int, validators=[Optional()])
    dificuldade = SelectField('Dificuldade', choices=[
        ('facil','Fácil'),('medio','Médio'),('dificil','Difícil')
    ])
    num_questoes = IntegerField('Nº de Questões', default=10,
                                   validators=[NumberRange(min=5, max=30)])
    inicio = StringField('Início (DD/MM/YYYY HH:MM)', validators=[DataRequired()])
    fim = StringField('Fim (DD/MM/YYYY HH:MM)',     validators=[DataRequired()])
    recompensa_xp_1 = IntegerField('XP 1º lugar',   default=500)
    recompensa_xp_2 = IntegerField('XP 2º lugar',   default=300)
    recompensa_xp_3 = IntegerField('XP 3º lugar',   default=150)
    recompensa_moedas_1 = IntegerField('Moedas 1º lugar', default=200)
    recompensa_moedas_2 = IntegerField('Moedas 2º lugar', default=100)
    recompensa_moedas_3 = IntegerField('Moedas 3º lugar', default=50)
    badge_temp = SelectField('Badge de Recompensa', choices=[
        ('','Nenhuma'),
        ('campeao-torneio','\U0001F3C6 Campeão Geral'),
        ('campeao-facil','\U0001F947 Campeão Fácil'),
        ('campeao-medio','\U0001F948 Campeão Médio'),
        ('campeao-dificil','\U0001F949 Campeão Difícil'),
        ('campeao-matematica','\U0001F4D0 Campeão Matemática'),
        ('campeao-historia','\U0001F4DC Campeão História'),
        ('campeao-ciencias','\U0001F52C Campeão Ciências'),
        ('campeao-portugues','\U0001F4D6 Campeão Português'),
        ('campeao-geografia','\U0001F30D Campeão Geografia'),
        ('campeao-fisica','\U000026A1 Campeão Física'),
        ('campeao-quimica','\U0001F9EA Campeão Química'),
        ('campeao-biologia','\U0001F9EC Campeão Biologia'),
    ], validators=[Optional()])
    submit = SubmitField('Criar Torneio')

    def validate_inicio(self, f):
        try:
            datetime.strptime(f.data, '%d/%m/%Y %H:%M')
        except Exception:
            raise ValidationError('Formato: DD/MM/YYYY HH:MM')

    def validate_fim(self, f):
        try:
            datetime.strptime(f.data, '%d/%m/%Y %H:%M')
        except Exception:
            raise ValidationError('Formato: DD/MM/YYYY HH:MM')
