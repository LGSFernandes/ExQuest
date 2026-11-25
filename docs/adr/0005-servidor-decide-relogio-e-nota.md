# ADR 0005: o servidor decide relógio, nota e ranking

**Status:** aceita

**Contexto:** simulados e competições com tempo e prêmios. Qualquer valor vindo do navegador pode ser forjado.

**Decisão:** o início da prova é gravado no servidor, o prazo é calculado lá (com tolerância curta de rede), a correção usa só os identificadores enviados e o gabarito fica oculto até a competição encerrar. O envio é único e reivindicado de forma atômica.

**Consequências:** o cronômetro do navegador é só cosmético. O encerramento depende de um comando agendado ou de visitas às páginas.
