# servidor/ — llama.cpp e modelos

```
bin/       llama-server, llama-cli, llama-bench  (links para /usr/bin)
modelos/   36 GGUF por link simbolico            (0 bytes duplicados)
logs/      modelo.log  ·  web.log
```

## Por que link simbolico e nao copia

Os GGUF do Pai somam ~200 GB em `/home/julianshin/Documentos/llm-models`.
Copiar para dentro do projeto duplicaria isso sem ganho nenhum. O link deixa a
pasta organizada e o disco em paz.

```bash
# ligar um modelo novo que apareceu la
ln -s /home/julianshin/Documentos/llm-models/NOVO.gguf servidor/modelos/

# trocar o binario do llama.cpp (ex.: uma build propria)
ln -sf /caminho/da/minha/build/llama-server servidor/bin/llama-server
```

## Subir na mao (o gatinho.sh faz isso sozinho)

```bash
servidor/bin/llama-server -m servidor/modelos/<modelo>.gguf \
  -ngl 99 -c 16384 --host 127.0.0.1 --port 8099 --jinja --flash-attn on
```

`-ngl 99` joga tudo na GPU. Numa RTX 3060 de 12 GB, modelo de 9B em Q4 cabe com
janela de 16K. Passando disso, o llama.cpp derrama para a RAM e fica lento.
