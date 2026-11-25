# ADR 0006: mensagens por polling

**Status:** aceita (com limite conhecido)

**Contexto:** chat entre amigos e grupos pequenos, em implantação de uma máquina com gunicorn síncrono.

**Decisão:** o navegador consulta novas mensagens a cada 4 segundos; imagens do chat são privadas, servidas por rota autorizada.

**Consequências:** simples e robusto, mas não é tempo real e gera requisições periódicas. Migrar para SSE ou WebSocket exigiria workers assíncronos e um barramento (Redis).
