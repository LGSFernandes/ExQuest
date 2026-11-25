"""Premium pré-pago: cada pagamento aprovado concede N dias (30 ou 365). Não há cobrança recorrente automática.
Upgrade vale na hora (o tempo restante do plano anterior NÃO é convertido); renovar o mesmo plano soma dias ao fim atual;
comprar plano inferior enquanto um superior está ativo é recusado."""
from datetime import timedelta

from app import clock
from app.extensions import db
from app.models import Assinatura, PagamentoHistorico, Usuario
from app.services import audit
from app.services.plans import CICLOS, PLANOS

ORDEM = list(PLANOS)  # basic < inter < advan


def validar_compra(usuario: Usuario, plano: str, ciclo: str) -> None:
    if plano not in PLANOS or ciclo not in CICLOS:
        raise ValueError("Plano inválido.")
    atual = usuario.plano_premium if usuario.premium_ativo else None
    if atual and ORDEM.index(plano) < ORDEM.index(atual):
        raise ValueError("Você já tem um plano superior ativo. Espere ele terminar para assinar um menor.")


def ativar(usuario: Usuario, plano: str, ciclo: str, pagamento) -> None:
    agora, dias = clock.agora(), CICLOS[ciclo]
    mesmo = usuario.premium_ativo and usuario.plano_premium == plano
    base = usuario.premium_expira if mesmo else agora
    for a in Assinatura.query.filter_by(usuario_id=usuario.id, status="ativa"):
        a.status, a.atualizado_em = "expirada" if mesmo or a.plano == plano else "substituida", agora
    usuario.plano_premium, usuario.premium_ciclo, usuario.premium_expira = plano, ciclo, base + timedelta(days=dias)
    usuario.premium_cancelar_em = None
    db.session.add(Assinatura(usuario_id=usuario.id, plano=plano, ciclo=ciclo, status="ativa", inicio=agora, expira=usuario.premium_expira,
                              renovacao_auto=False, provider=pagamento.provider, provider_assinatura_id=str(pagamento.id)))
    db.session.add(PagamentoHistorico(usuario_id=usuario.id, plano=plano, ciclo=ciclo, valor=pagamento.valor_centavos / 100,
                                      status="pago", descricao=pagamento.descricao))
    audit.registrar("premium_ativado", usuario.id, f"{plano}/{ciclo} pg={pagamento.id}")


def revogar(usuario: Usuario, pagamento) -> None:
    """Reembolso/contestação: retira os dias que esse pagamento concedeu."""
    agora = clock.agora()
    if usuario.premium_expira:
        nova = usuario.premium_expira - timedelta(days=CICLOS.get(pagamento.ciclo, 0))
        if nova <= agora:
            usuario.plano_premium = usuario.premium_ciclo = usuario.premium_expira = None
        else:
            usuario.premium_expira = nova
    for a in Assinatura.query.filter_by(usuario_id=usuario.id, provider_assinatura_id=str(pagamento.id)):
        a.status, a.atualizado_em = "reembolsada", agora
    db.session.add(PagamentoHistorico(usuario_id=usuario.id, plano=pagamento.plano, ciclo=pagamento.ciclo,
                                      valor=pagamento.valor_centavos / 100, status="reembolsado", descricao=pagamento.descricao))
    audit.registrar("premium_revogado", usuario.id, f"pg={pagamento.id}")


def expirar_vencidos() -> int:
    """Marca assinaturas vencidas (o acesso em si já é calculado pela data) e limpa o plano do usuário."""
    agora, n = clock.agora(), 0
    for a in Assinatura.query.filter(Assinatura.status == "ativa", Assinatura.expira < agora):
        a.status, a.atualizado_em, n = "expirada", agora, n + 1
    return n
