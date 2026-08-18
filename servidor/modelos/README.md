# Modelos

Os `.gguf` moram **aqui**, arquivo real — não atalho, não cópia.

O `.gitignore` barra `servidor/modelos/*.gguf`, então o repositório sobe leve e você
baixa o que quiser nesta pasta. Nada mais precisa ser configurado: o Gatinho varre
este diretório na inicialização e tudo que estiver aqui aparece em `/model`.

```bash
cd servidor/modelos
# escolha um dos três abaixo e baixe só o arquivo Q4_K_M
```

---

## Três que rodam bem no Gatinho

Todos são de 9B, cabem em **~5,5 GB** em `Q4_K_M` e rodam em GPU de 8 GB com
`-ngl 99`. A janela padrão do projeto é 16K (`CTX=32768 ./gatinho.sh` aumenta).

| Modelo | Arquivo | Tamanho | Onde baixar |
|---|---|---:|---|
| **OmniCoder-9B** — o padrão sugerido; segue instrução de ferramenta com disciplina, que é o que um agente de código precisa | `omnicoder-9b-q4_k_m.gguf` | ~5,4 GB | [Tesslate/OmniCoder-9B-GGUF](https://huggingface.co/Tesslate/OmniCoder-9B-GGUF) · [pesos originais](https://huggingface.co/Tesslate/OmniCoder-9B) |
| **Qwen3.5-9B Opus Distill v2** — melhor de raciocínio; escreve código mais elaborado, e às vezes elabora demais | `Qwen3.5-9B-Opus-Distill-v2-Q4_K_M.gguf` | ~5,3 GB | [Jackrong/…Opus-Reasoning-Distilled-v2-GGUF](https://huggingface.co/Jackrong/Qwen3.5-9B-Claude-4.6-Opus-Reasoning-Distilled-v2-GGUF) |
| **DeepSeek-V4-Pro-Qwen3.5-9B MTP** — o mais leve de exigência; bom para tarefa curta e resposta rápida | `DeepSeek-V4-Pro-Qwen3.5-9B-MTP-Q4_K_M.gguf` | ~5,4 GB | [Jackrong/DeepSeek-V4-Pro-Qwen3.5-9B-MTP-GGUF](https://huggingface.co/Jackrong/DeepSeek-V4-Pro-Qwen3.5-9B-MTP-GGUF) |

Os três são recomendação de uso, **não um ranking**. A avaliação comparativa que
originou a escolha é trabalho próprio e não faz parte deste repositório — não há
notas, tabela de posições nem tarefas de teste publicados aqui.

### Baixando

`huggingface-cli` pega só o arquivo que interessa, sem clonar o repositório inteiro:

```bash
pip install -U "huggingface_hub[cli]"
huggingface-cli download Tesslate/OmniCoder-9B-GGUF \
  --include "*Q4_K_M.gguf" --local-dir .
```

Sem a CLI, `wget -c` no link direto resolve — e o `-c` importa: link assinado de CDN
expira no meio do download, e sem continuação você recomeça do zero.

---

## Usando

```bash
./gatinho.sh                                  # sobe o primeiro .gguf que encontrar
MODELO=omnicoder ./gatinho.sh                 # escolhe por pedaço do nome
CTX=32768 ./gatinho.sh                        # janela maior
```

Na interface, `/models` lista o que está nesta pasta e `/model` abre o seletor.
Trocar por ali **reinicia o llama-server** com o novo arquivo e só confirma depois
de perguntar ao servidor qual arquivo ele está servindo — `/health` respondendo `ok`
não prova qual modelo está carregado, e confiar nisso já produziu uma bateria
inteira de medições contra o modelo errado.

## Quantização

`Q4_K_M` é o ponto de equilíbrio para estes 9B: cabe em 8 GB de VRAM e mantém a
qualidade de código. `Q5_K_M` e `Q6_K` melhoram um pouco e custam 1–2 GB a mais.
Abaixo de `Q4` a qualidade cai rápido — vale experimentar em texto, não em código.
