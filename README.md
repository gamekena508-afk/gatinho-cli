# 🐱 Gatinho CLI

Agente de código para modelo local. Interface no navegador, motor de verdade.

```bash
./gatinho.sh                  # liga o modelo, sobe a interface, abre o navegador
./gatinho.sh ~/meu-projeto    # trabalha lendo outro projeto
```

O `gatinho.sh` confere a RAM, confere o venv, sobe o `llama-server` (ou reaproveita
um que já esteja no ar), sobe a interface e abre o navegador. `Ctrl+C` derruba
**só o que ele subiu**.

---

## O projeto

```
gatinho-cli/
├── gatinho.sh          ← liga tudo. É por aqui que se começa.
├── venv/               ambiente virtual do projeto (ver "O ambiente")
├── requirements.txt
│
├── gatinho/            o motor
│   ├── app.py          CLI do terminal e o modo --serve
│   ├── servidor.py     HTTP + SSE: a ponte navegador ↔ motor
│   ├── runtime.py      planeja, roteia, executa, mede
│   ├── roteador.py     V3.1 — escolhe fast-coder ou mast-agent
│   ├── motor.py        dono do llama-server: sobe, derruba e TROCA de modelo
│   ├── sandbox.py      works/ — uma pasta por sessão
│   ├── i18n.py         detecta idioma e traduz (pt · en · es · zh)
│   ├── comandos.py     registro central dos /comandos (a paleta da web le daqui)
│   ├── handlers.py     um handler por comando (58 comandos)
│   ├── sessao.py       persistência e compactação
│   ├── config.py       configuração em 4 camadas
│   ├── capacidades.py  registry de modelos e providers
│   ├── metricas.py     emitidas / executadas / bloqueadas
│   ├── skills.py       skills (reaproveita ~/.claude/skills)
│   ├── estado.py       o Contexto que tudo compartilha
│   └── ui.py           desenho do terminal
│
├── servidor/           llama.cpp e modelos, organizados
│   ├── bin/            llama-server, llama-cli, llama-bench (links)
│   ├── modelos/        os .gguf de verdade + README com o que baixar
│   └── logs/           modelo.log e web.log
│
├── web/                a interface oficial
│   ├── index.html      gerado — não edite à mão
│   ├── gerar.py        monta o index.html
│   └── assets/         a arte do gato
│
├── works/              ← o agente trabalha AQUI, uma pasta por sessão
├── testes/             83 testes + o provador de mutação + as duas auditorias
└── bin/gatinho         o executável
```

---

## O ambiente

O venv é criado com `--system-site-packages` **de propósito**: assim o projeto
enxerga o torch/CUDA que já está no pyenv, sem rebaixar 3 GB de novo.

O preço disso é uma armadilha, e ela já pegou aqui: com o sistema visível, o `pip`
responde *"already satisfied"* e **não instala nada**. A pasta `venv/` existe,
`import rich` funciona, e mesmo assim as três dependências vêm do python global.
Foi exatamente o estado encontrado em 2026-08-17 — venv de 0 pacotes próprios.

```bash
venv/bin/pip install --ignore-installed -r requirements.txt
```

O `--ignore-installed` não é preciosismo: é o que faz o venv existir de verdade.
O `gatinho.sh` confere isso sozinho — e não pelo `import`, que passa dos dois
jeitos, e sim por **de onde o módulo resolve**.

A auditoria cobra o mesmo invariante, e ele sabe reprovar: escondendo o `rich` do
venv, ela acusa `rich /home/julianshin/.pyenv/…` e devolve 1 invariante violado.

---

## Modelos e a troca de modelo

Os `.gguf` ficam em `servidor/modelos/`, **arquivo real** — não atalho, não cópia.
O `.gitignore` barra `*.gguf`, então o repositório sobe leve; o
[README de lá](servidor/modelos/README.md) diz o que baixar.

`/model` abre o seletor e **troca o modelo de verdade**: derruba o `llama-server`,
sobe outro com o novo arquivo e só confirma depois de perguntar qual arquivo está
carregado. Isso importa porque `/health` respondendo `ok` não prova nada — num
benchmark meu, um servidor esquecido segurando a porta fez 29 medições rodarem
contra o modelo errado sem ninguém notar.

Três coisas que o comando se recusa a fazer, e cada uma tem teste:

- derrubar um `llama-server` que este projeto não subiu;
- dizer "modelo alterado" quando a troca falhou — a configuração volta ao anterior;
- ficar com o estado divergindo do motor: ao subir, quem manda é o arquivo servido.

A paleta de `/` na web vem de `GET /api/comandos`, o registro real. Antes era uma
lista escrita à mão com 8 nomes, três inexistentes, enquanto 50 comandos reais —
inclusive `/model` — não apareciam. Os apelidos em português funcionam:
`/modelo`, `/limpar`, `/modo`, `/ajuda`, `/ferramentas`, `/sair`.

---

## Sandbox: o agente não mexe no teu projeto

**Padrão: `works/<data>-<hora>-<sessão>/`.** Cada conversa ganha a própria pasta,
semeada com uma cópia do teu código (só arquivos de texto, sem `node_modules`, sem
binário grande, sem seguir link simbólico).

A razão está medida, não é paranoia: no `harness-bench` um modelo local deixou um
`}` solto e matou o módulo inteiro; outro editou o **arquivo de teste** em vez de
consertar o código. Numa pasta descartável isso é um experimento. No teu projeto,
é estrago.

```
/sandbox        onde estou escrevendo agora
/sandbox on     trabalha na cópia (padrão)
/sandbox off    escreve no projeto de verdade — aparece como AVISO, não como "ok"
/works          lista as pastas · /works apagar <nome>
```

Na barra de status aparece `🧪 works/…` quando está na sandbox, e o mesmo chip fica
**vermelho** quando você libera o acesso direto.

**Provado:** rodei um pedido em `/tmp/proj-i18n`; o agente criou `greet.py` dentro de
`works/20260817-1947-…/` e a pasta original continuou com **só** o `original.py`.

---

## Idiomas: pt-BR · English · español · 中文

Detecta pelo que **você** escreve e muda duas coisas:

1. **a interface** — placeholder, abas, barra, rodapé, avisos;
2. **o idioma da resposta** — por instrução no system prompt, não por tradução
   automática do texto do modelo. Traduzir a saída dele com tabela daria texto
   quebrado; pedir que ele escreva no idioma certo funciona melhor e é honesto.

```
/idioma          escolhe na lista
/idioma en       fixa
/idioma auto     volta a detectar sozinho
```

Sinal fraco não troca nada: um `"ok"` no meio da conversa não vira a interface de
cabeça pra baixo.

**Provado em espanhol:** `modo: PLANIFICACIÓN` · `[Consejo] / comandos | Ctrl+L limpiar`
· e a frase do agente: *"Listo: creé saludo.py. Validé ejecutando la verificación (1x)."*

---

## Servidor e modelos

`servidor/modelos/` tem **36 GGUF por link simbólico** — nenhum byte duplicado dos
teus 200 GB. `servidor/bin/` liga os binários do llama.cpp. Os logs ficam em
`servidor/logs/`.

```bash
MODELO=omnicoder-9b ./gatinho.sh         # escolhe outro
PORTA=9000 ./gatinho.sh                  # outra porta da interface
SEM_MODELO=1 ./gatinho.sh                # já tem llama-server no ar
CTX=32768 ./gatinho.sh                   # janela maior
```

---

## O que aparece na tela é o que aconteceu no disco

Cada `Wrote`, `Edited` e `Ran` é ferramenta real executando. O texto vem do modelo
em streaming. A barra mostra **AO VIVO** em verde.

As ferramentas vêm do `harness-filho`, com as guardas já medidas: escrita verificada
com rollback por sintaxe, `edit` de um bloco só, no-op tratado como erro explicado,
leitura obrigatória antes de editar. E o agente **não encerra dizendo "pronto"** sem
ter rodado uma verificação.

Métrica sempre separada — `emitidas` ≠ `executadas` ≠ `bloqueadas`. Confundir isso
já produziu um diagnóstico errado num benchmark: um modelo *pediu* 139 ações e teve
**5** executadas.

---

## Testes

```bash
venv/bin/python -m pytest testes/ -q     # 83 testes
venv/bin/python testes/provar_suite.py   # prova que a suíte sabe REPROVAR
venv/bin/python testes/auditoria.py      # os 58 comandos + invariantes
venv/bin/python testes/auditar_web.py    # os mesmos comandos pelo HTTP, como a web faz
```

O segundo importa mais: quebra o código de propósito em 6 pontos e cobra que a suíte
acuse cada um. Foi assim que peguei um teste decorativo meu.

---

## Limites honestos

- o servidor escuta só em `127.0.0.1` e **não tem autenticação** — quem estiver na
  máquina alcança. Expor na rede exige senha antes, e isso é decisão do dono;
- a semente da sandbox para em 400 arquivos ou 8 MB — projeto gigante entra parcial;
- a detecção de idioma é por heurística, sem biblioteca externa; texto muito curto
  mantém o idioma anterior de propósito;
- `/undo` e `/rollback` cobrem o que o agente escreveu **nesta sessão**, em memória —
  não substituem git;
- streaming token a token existe na web; no terminal a resposta aparece ao fim do turno.
