"""Pacote de modelos. `from app.models import Usuario` continua funcionando (compatibilidade)."""
from app.models.competition import (TORNEIO_CONFIG, Torneio, TorneioParticipante, TorneioQuestao,  # noqa: F401
                                    TorneioResposta)
from app.models.content import Alternativa, Materia, Questao, QuestaoRespondidaSessao, RespostaUsuario  # noqa: F401
from app.models.economy import (AdsCredit, Assinatura, CompraMoedas, EventoWebhook, InventarioItem,  # noqa: F401
                                ItemLoja, LancamentoCarteira, OfertaTrial, Pagamento, PagamentoHistorico,
                                RecompensaNivelConcedida, XpEvento)
from app.models.jobs import Job  # noqa: F401
from app.models.rum import MetricaRum  # noqa: F401
from app.models.social import (Amizade, Bloqueio, Denuncia, GrupoChat, GrupoConfig, GrupoMembro,  # noqa: F401
                               Mensagem, Notificacao)
from app.models.study import Colecao, ColecaoItem, MissaoProgresso, RevisaoQuestao, SimuladoSessao  # noqa: F401
from app.models.system import ConteudoBloqueado, LogAuditoria, TokenRecuperacao  # noqa: F401
from app.models.user import Streak, Usuario, load_user  # noqa: F401
