# ADR 0001: monólito Flask com camada de serviços

**Status:** aceita

**Contexto:** o código original concentrava rotas, regras e acesso a dados em um só arquivo. A equipe é pequena e o deploy é uma única máquina.

**Decisão:** manter um monólito (app factory, blueprints finos), com regras em `app/services/` e modelos em pacote. Sem microsserviços nem filas.

**Consequências:** simples de operar e testar; regras reutilizáveis (competições e missões usam as mesmas peças de XP e carteira). Escalar horizontalmente exige Redis para o limitador e banco compartilhado.
