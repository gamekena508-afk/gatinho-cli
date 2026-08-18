# Gatinho CLI — interface web (a oficial)

```bash
./gatinho.sh                 # da raiz do projeto: liga o modelo, sobe e abre o navegador
./gatinho.sh ~/meu-projeto   # trabalha noutra pasta
```

O `gatinho.sh` confere a RAM, sobe o `llama-server` (ou reaproveita um que já esteja
no ar), sobe a interface e abre o navegador. `Ctrl+C` derruba **só o que ele subiu**.

**Isso é real.** Cada `Wrote`, `Edited` e `Ran` que aparece na tela é uma ferramenta
executando no disco, e o texto vem do modelo em streaming (SSE). A barra mostra
`AO VIVO` em verde quando está ligado no motor.

Aberto direto (duplo clique, `file://`) ele continua funcionando, mas como **DEMO** —
a barra mostra `DEMO (sem servidor)` em amarelo e as respostas são roteiro fixo,
marcado com `[DEMO]`. Sem fingir que é real.

```
web/
├── index.html        a interface (31 KB) — gerada, não edite à mão
├── gerar.py          monta o index.html a partir do CSS/HTML/JS e da arte
├── assets/
│   ├── gatinho.png          arte tratada, 4,5 KB, transparente  ← usada
│   ├── gatinho-mini.png     0,7 KB, para a barra da conversa
│   └── gatinho-original.png o PNG que o Pai mandou, 863 KB (guardado)
└── README.md
```

Para mexer: edite `gerar.py` e rode `python3 gerar.py`.

## As duas telas, num arquivo só

| Estado | O que aparece | Como chega |
|---|---|---|
| **inicial** | gato grande, título em blocos, ficha do modo, abas, log e stats | ao abrir, `/limpar`, `Ctrl+L`, botão `◀ início`, `Esc` |
| **conversa** | barra compacta com o gato mini, bolhas de você/Gatinho, tools, código, diff, "Worked for" | ao mandar a primeira mensagem |

O input, a barra de status (modo · tempo · tokens · modelo) e o rodapé de dicas
ficam **sempre visíveis**, nas duas telas. Os modos (`PLANEJAMENTO` / `FULL ACESSO` /
`PEDIR PERMISSÃO`) são o mesmo estado nas duas — trocar na aba muda o botão da
conversa e vice-versa.

## A arte do gato

O HTML original apontava para
`https://chatgpt.com/backend-api/estuary/content?...&sig=...` — **link assinado, que
expira**. Quando expirasse, a interface abriria sem gato.

Agora a arte mora no projeto e vai **embutida em base64** no `index.html`.
Zero request externo, e o arquivo abre em qualquer máquina.

O PNG que o Pai mandou tinha **fundo preto opaco**. O painel do CLI é `#0a0906`, não
`#000` — colado cru, apareceria um retângulo mais escuro em volta do gato. Tratamento
aplicado no `gerar.py`:

| Passo | Antes | Depois |
|---|---|---|
| preto vira transparente | fundo `#000` sólido | alpha 0 |
| recorte da moldura vazia | 1254×1254 | 989×853 |
| alpha binário + cor do tema | 24.520 cores (antialias) | 1 cor (`#f0a924`) |
| tamanho | 863 KB | **4,5 KB** |

`NEAREST` no redimensionamento, para o pixel continuar cravado. A grade escura entre
os blocos virou transparência — é ela que dá o desenho.

Clicar no gato (ou `[V]`) troca por variantes em ASCII; `[C]` esconde; `[S]` esconde
as stats. Se a imagem falhar por qualquer motivo, o `onerror` cai no gato ASCII.

## Como o navegador fala com o motor

```
GET  /             a interface
GET  /api/estado   modelo, modo, contexto, harness, arquivos tocados
POST /api/chat     {"texto": "..."} -> SSE: plano · ação · resultado · texto · fim
POST /api/comando  {"texto": "/status"} -> passa pelo mesmo command router do terminal
POST /api/parar    interrompe a execução
```

Um servidor por vez (trava): duas abas não disputam o mesmo projeto.

## Prova de que é real

Rodado em `/tmp/proj-real`, pela interface do navegador:

```
tela:   • Wrote saudacao.py  • Wrote test_saudacao.py  • Ran pytest -q
        exit=0 · 1 passed in 0.00s
        ─ 6.90s · tools 6 executadas / 6 emitidas · 9 turnos ─

disco:  saudacao.py  test_saudacao.py
$ pytest -q  →  1 passed          (rodado por fora, na mão)
```

E numa segunda run: `dobro.py` criado, `dobro(21) = 42` conferido fora da interface.

## Testado no navegador de verdade

Não é "abriu, então está bom" — a interface foi dirigida:

- tela inicial e tela de conversa alternam certo (`#viewHome` / `#viewChat`);
- imagem carrega (`complete && naturalWidth > 0`);
- `/mo` abre o autocomplete;
- `/modo plan` muda a aba **e** a barra de status juntas;
- fluxo PLAN → o agente pergunta → `sim` → vira FULL ACESSO e implementa com codeblock;
- fluxo PERM → pede permissão → `n` → registra o bloqueio;
- `/limpar` volta ao início e esvazia a conversa;
- **zero erros de JS** no console em todos os caminhos.

## Defeitos que apareceram no teste e foram corrigidos

1. **Buraco no rodapé da tela inicial** — o `min-height:88vh` (que a conversa precisa)
   esticava o painel também no início. Agora só vale com `.cli.chat-on`.
2. **"pensando…" abria um card separado** da resposta — pensar e responder são a mesma
   fala do agente. `cardAtual()` reaproveita o card aberto; o "Worked for" fecha.
3. **Contador de tokens ficava em `0.0K`** na execução real — com `stream:true` o
   llama-server só manda `usage` se você pedir `stream_options:{include_usage:true}`.
4. **O roteador dizia "escolha manual do usuário"** quando na verdade era o padrão —
   a V3.1 tornou o `mast-agent` default, então a mensagem enganava na tela.
