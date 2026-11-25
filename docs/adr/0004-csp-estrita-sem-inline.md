# ADR 0004: CSP estrita sem estilo ou script inline

**Status:** aceita

**Contexto:** defesa em profundidade contra XSS, com conteúdo gerado por usuários (questões, chat, perfis) e LaTeX.

**Decisão:** `script-src 'self'` e sem `style=`. Valores dinâmicos usam `data-vars`, aplicados por CSSOM em `app.js`. KaTeX e ícones são locais, e a renderização do LaTeX constrói DOM em vez de `innerHTML`. JSON-LD é bloco de dados, serializado com `tojson`.

**Consequências:** qualquer biblioteca externa precisa ser servida localmente; estilos dinâmicos têm um caminho único.
