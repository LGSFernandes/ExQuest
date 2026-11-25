# ADR 0002: carteira com ledger e chaves de idempotência

**Status:** aceita

**Contexto:** moedas e XP vinham de vários fluxos (respostas, missões, competições, pagamentos) e podiam ser concedidos em duplicidade por cliques ou webhooks repetidos.

**Decisão:** todo movimento é um lançamento imutável com chave única (`resposta:uid:qid`, `missao:...`, `torneio:...`). O saldo em `usuarios.moedas` é denormalizado e a verdade é o ledger. Reivindicações usam UPDATE condicional ou unicidade do banco, nunca verificar-depois-gravar.

**Consequências:** repetir qualquer operação é seguro; estornos são lançamentos. Todo novo fluxo de recompensa precisa de uma chave determinística.
