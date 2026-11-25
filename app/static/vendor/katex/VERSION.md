# KaTeX (vendorizado)

- Versão: **0.16.47** (confirmada em `katex.min.js`)
- Licença: MIT (`LICENSE` nesta pasta)
- Origem: https://github.com/KaTeX/KaTeX/releases (arquivos `katex.min.js`, `katex.min.css`, `fonts/`, `contrib/auto-render.min.js`)
- Por que vendorizado: a CSP do ExQuest só permite `script-src 'self'` e fontes próprias; sem CDN.
- Atualização: baixar a nova versão oficial, substituir estes arquivos, atualizar este documento e rodar a suíte.
- Modificação local: `katex.min.css` só referencia `.woff2` e as fontes `.woff`/`.ttf` foram removidas (todo navegador com `dialog`/CSS layers, exigidos pelo ExQuest, lê WOFF2). Ao atualizar, repita: remover as entradas `url(...woff)`/`url(...ttf)` do CSS e apagar esses arquivos.
