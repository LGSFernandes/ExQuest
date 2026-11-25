# Auditoria de segurança do ExQuest (run-1)

**Modo e perfil:** auditoria completa, perfil padrão, 10 unidades de cobertura, 1 onda de caçadores (um por unidade). Alvo: `/home/claude/ExQuest`, código-fonte apenas.

**Limites desta auditoria (leia antes dos resultados)**
- Não havia sandbox de SO para executar código do alvo. Os caçadores leram somente o código; o agente principal rodou os testes do próprio projeto (pytest) para reproduzir e corrigir.
- Os achados abaixo foram **corrigidos pelo próprio agente que os recebeu**, com teste de regressão. Nenhum passou por verificador independente (um agente que não viu a correção). Por isso `findings.json` está vazio: o contrato do skill exige demonstração independente para "confirmed", e ela não foi feita.
- Não houve segunda onda nem crítico de cobertura. Cada unidade foi vista por um caçador, uma vez.
- Cinco rodadas de agentes falharam por limite de uso do plano antes de esta onda completar; foram refeitas.

## Resultado

Seis defeitos de código encontrados, todos corrigidos e cobertos por teste (186 testes passando ao final). Nenhum permitia execução de código, acesso a banco inteiro ou tomada de contas sem uma sessão válida.

| # | Achado | Gravidade estimada | Estado |
|---|---|---|---|
| 1 | Cookie "lembrar de mim" continuava valendo depois de trocar a senha (guardava só o id do usuário). Reproduzido com teste antes da correção | média | Corrigido: identificador `id:session_version`, validade de 30 dias |
| 2 | Lista de conversas mostrava prévia (60 caracteres) e contagem de mensagens anteriores à entrada no grupo | baixa | Corrigido |
| 3 | Criar grupo ignorava bloqueio entre dois convidados | baixa | Corrigido |
| 4 | Simulado criado antes da inscrição numa competição corrigia as questões da competição e revelava "Correta/Incorreta" (oráculo de gabarito) e pagava XP | média | Corrigido: questões travadas não são corrigidas |
| 5 | GIF: o orçamento de pixels só era conferido depois de varrer até 301 quadros | baixa (custo não medido) | Corrigido: o orçamento limita a varredura |
| 6 | Imagem e denúncia de mensagem de grupo ignoravam o corte por data de entrada | baixa | Corrigido |

## Endurecimentos aplicados
Token de redefinição só por hash e consumo atômico; link de notificação sem barra invertida; revisão recusa questão desativada; exclusão de conta sem senha exige login recente (10 min); e-mails pendentes na fila são cancelados ao excluir a conta; corpo do beacon RUM limitado sem depender de Content-Length; assinatura não-ASCII em webhook não gera erro 500; `Vary: X-Fragmento`; vínculo Google recusa e-mail já ligado a outro `sub`; MP_SANDBOX lido como booleano; nginx sem confiar em `X-Forwarded-Host`; catch-all 444 no nginx de borda; auditoria registra IP nas ações de competição.

## Riscos residuais (decisão do responsável)
- Limitador de requisições em `memory://` por padrão: com várias réplicas os limites por IP se multiplicam. Defina `RATELIMIT_STORAGE_URI` para um Redis.
- Fila de e-mails: com `JOBS_MODE=queue`, o payload pendente contém o link de redefinição em texto até o envio (poucos minutos); vazamento só com acesso de leitura ao banco.
- Exportação de dados da conta não exige senha/login recente (rate limit e `no-store` aplicados).
- Webhook do Mercado Pago sem tolerância de timestamp (repetição só reconsulta o provedor e é deduplicada).
- Moedas gastas antes de um estorno não são recuperadas (decisão de negócio já documentada).
- Pastas públicas antigas de chat (`chat_files`, `chat_imgs`) não são migradas automaticamente: verifique e apague se existirem em produção.
- Login por Google não força nova autenticação (`prompt=login`) na exclusão de conta.

## Cobertura
10 de 10 unidades revisadas uma vez, em modo somente leitura. Não há ledger de execução anterior. Ver `coverage-ledger.json`. Não é prova de ausência de vulnerabilidades.
