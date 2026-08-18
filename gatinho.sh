#!/usr/bin/env bash
# Gatinho CLI — liga o modelo, sobe a interface e abre o navegador.
#
#   ./gatinho.sh                      usa o padrao (deltacoder-9b, pasta atual)
#   ./gatinho.sh ~/meu-projeto        trabalha noutra pasta
#   MODELO=omnicoder-9b ./gatinho.sh
#   PORTA=9000 ./gatinho.sh
#   SEM_MODELO=1 ./gatinho.sh         nao sobe llama-server (ja tem um no ar)
#
# Ctrl+C encerra tudo que este script subiu — e so o que ele subiu.
set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJETO="${1:-$PWD}"
mkdir -p "$RAIZ/servidor/logs" "$RAIZ/works"
PORTA="${PORTA:-8777}"
PORTA_MODELO="${PORTA_MODELO:-8099}"
MODELO="${MODELO:-deltacoder-9b}"
MODELOS_DIR="${MODELOS_DIR:-$RAIZ/servidor/modelos}"
LLAMA_BIN="${LLAMA_BIN:-$RAIZ/servidor/bin/llama-server}"
PY="$RAIZ/venv/bin/python"
LOGS="$RAIZ/servidor/logs"
CTX="${CTX:-16384}"
NGL="${NGL:-99}"
MEM_MIN_GB="${MEM_MIN_GB:-9}"

A="\033[38;5;214m"; V="\033[32m"; R="\033[31m"; C="\033[90m"; Z="\033[0m"
ok(){ printf "  ${V}✓${Z} %s\n" "$1"; }
erro(){ printf "  ${R}✗${Z} %s\n" "$1"; }
info(){ printf "  ${C}·${Z} %s\n" "$1"; }

PID_MODELO=""
PID_WEB=""
PID_NAV=""
NAV_ISOLADO=0     # 1 so quando o navegador roda em perfil descartavel nosso
limpar() {
  echo
  info "encerrando…"
  [ -n "$PID_WEB" ] && kill "$PID_WEB" 2>/dev/null
  # so derruba o llama-server se FOMOS NOS que subimos
  [ -n "$PID_MODELO" ] && kill "$PID_MODELO" 2>/dev/null && ok "modelo derrubado"
  # e o navegador: medido em 2026-08-18, o Ctrl+C deixava 9 processos de Chrome
  # vivos. Isso ja custou uma sessao inteira por falta de memoria. So encerramos
  # o perfil descartavel /tmp/gatinho-perfil — o navegador pessoal, com as abas
  # do dono, nunca e tocado (por isso NAV_ISOLADO existe).
  if [ "$NAV_ISOLADO" = 1 ] && [ -n "$PID_NAV" ]; then
    kill -- "-$PID_NAV" 2>/dev/null || kill "$PID_NAV" 2>/dev/null
    ok "navegador do gatinho encerrado"
  fi
  exit 0
}
trap limpar INT TERM

printf "${A}"
cat <<'GATO'
   /\_/\    GATINHO CLI
  ( ^.^ )   interface no navegador
   > ^ <
GATO
printf "${Z}\n"

# ---------------------------------------------------------------- memoria
# Licao de 2026-08-17: a sessao morreu por OOM com o modelo carregado sem folga.
LIVRE_KB=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo 2>/dev/null || echo 99999999)
LIVRE_GB=$(( LIVRE_KB / 1048576 ))
if [ "$LIVRE_GB" -lt "$MEM_MIN_GB" ] && [ -z "${SEM_MODELO:-}" ]; then
  erro "so ${LIVRE_GB} GB de RAM livres; o modelo pede ~${MEM_MIN_GB} GB."
  info "feche o que estiver pesado, ou rode com SEM_MODELO=1 se ja houver servidor no ar."
  exit 1
fi
ok "memoria: ${LIVRE_GB} GB livres"

# ---------------------------------------------------------------- ambiente
if [ ! -x "$PY" ]; then
  erro "ambiente virtual nao encontrado em venv/"
  info "crie com:  python3 -m venv --system-site-packages venv && venv/bin/pip install --ignore-installed -r requirements.txt"
  exit 1
fi
if ! "$PY" -c "import sys, prompt_toolkit, rich, pytest
assert all(m.__file__.startswith(sys.prefix) for m in (prompt_toolkit, rich, pytest))" 2>/dev/null; then
  info "instalando dependencias DENTRO do venv…"
  # --ignore-installed e obrigatorio: com --system-site-packages o pip enxerga os
  # pacotes do pyenv, responde "already satisfied" e nao instala nada. O venv fica
  # uma casca, e o projeto passa a depender do python global sem ninguem perceber.
  "$PY" -m pip install -q --ignore-installed -r "$RAIZ/requirements.txt" \
    || { erro "falhou instalar"; exit 1; }
fi
ok "venv: $("$PY" --version 2>&1)"

if [ ! -e "$LLAMA_BIN" ]; then
  erro "llama-server nao encontrado em servidor/bin/"
  info "ligue com:  ln -s \$(command -v llama-server) servidor/bin/llama-server"
  exit 1
fi

# ---------------------------------------------------------------- modelo
porta_viva(){ (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null && exec 3>&- && return 0 || return 1; }

if [ -n "${SEM_MODELO:-}" ]; then
  info "SEM_MODELO=1 — nao vou subir llama-server"
elif porta_viva "$PORTA_MODELO"; then
  SERVIDO=$(curl -s "http://127.0.0.1:${PORTA_MODELO}/v1/models" 2>/dev/null \
            | sed -n 's/.*"model":"\([^"]*\)".*/\1/p' | head -1)
  ok "ja tem modelo servindo na ${PORTA_MODELO}: $(basename "${SERVIDO:-desconhecido}")"
else
  GGUF=$(ls "$MODELOS_DIR" 2>/dev/null | grep -i "${MODELO%%-*}" | grep -i '\.gguf$' | head -1)
  [ -z "$GGUF" ] && GGUF=$(ls "$MODELOS_DIR"/*.gguf 2>/dev/null | head -1 | xargs -r basename)
  if [ -z "$GGUF" ]; then
    erro "nao achei nenhum .gguf em $MODELOS_DIR"; exit 1
  fi
  info "subindo llama-server com $GGUF"
  "$LLAMA_BIN" -m "$MODELOS_DIR/$GGUF" -ngl "$NGL" -c "$CTX" \
    --host 127.0.0.1 --port "$PORTA_MODELO" --jinja --flash-attn on \
    --cont-batching --no-webui > "$LOGS/modelo.log" 2>&1 &
  PID_MODELO=$!
  printf "  ${C}·${Z} carregando o modelo"
  for _ in $(seq 1 90); do
    if curl -s "http://127.0.0.1:${PORTA_MODELO}/health" 2>/dev/null | grep -q ok; then
      echo; ok "modelo pronto na porta ${PORTA_MODELO}"; break
    fi
    if ! kill -0 "$PID_MODELO" 2>/dev/null; then
      echo; erro "o llama-server morreu. Ultimas linhas:"
      tail -5 "$LOGS/modelo.log" | sed 's/^/      /'
      exit 1
    fi
    printf "."; sleep 2
  done
  if ! curl -s "http://127.0.0.1:${PORTA_MODELO}/health" 2>/dev/null | grep -q ok; then
    echo; erro "o modelo nao respondeu a tempo (veja servidor/logs/modelo.log)"; exit 1
  fi
  # Entrega o PID ao python: sem isto o /model se recusa a trocar de modelo, porque
  # o motor.py — com razao — nao derruba processo que ele nao sabe que e nosso.
  # Medido em 2026-08-18: a troca respondia "nao vou derrubar processo dos outros"
  # falando do llama-server que o proprio ./gatinho.sh tinha acabado de subir.
  export GATINHO_MODELO_PID="$PID_MODELO"
fi
export PORTA_MODELO

# ---------------------------------------------------------------- interface
if porta_viva "$PORTA"; then
  erro "a porta ${PORTA} ja esta ocupada. Use PORTA=9000 ./gatinho.sh"; exit 1
fi
[ -f "$RAIZ/web/index.html" ] || "$PY" "$RAIZ/web/gerar.py" >/dev/null

"$PY" "$RAIZ/bin/gatinho" --serve --porta "$PORTA" --cwd "$PROJETO" \
  > "$LOGS/web.log" 2>&1 &
PID_WEB=$!
for _ in $(seq 1 40); do porta_viva "$PORTA" && break; sleep 0.25; done
if ! porta_viva "$PORTA"; then
  erro "a interface nao subiu. Log:"; tail -8 "$LOGS/web.log" | sed 's/^/      /'
  limpar
fi
URL="http://127.0.0.1:${PORTA}"
ok "interface no ar: ${URL}"
info "projeto: ${PROJETO}"

# ---------------------------------------------------------------- navegador
abriu=0
for nav in google-chrome-stable chromium firefox xdg-open; do
  command -v "$nav" >/dev/null 2>&1 || continue
  case "$nav" in
    google-chrome-stable|chromium)
      setsid "$nav" --user-data-dir=/tmp/gatinho-perfil --no-first-run \
        --no-default-browser-check --new-window --app="$URL" >/dev/null 2>&1 &
      PID_NAV=$!; NAV_ISOLADO=1 ;;
    *) setsid "$nav" "$URL" >/dev/null 2>&1 & ;;
  esac
  abriu=1; ok "abri no ${nav}"; break
done
[ "$abriu" = 0 ] && info "abra na mao: ${URL}"

echo
printf "  ${A}o gatinho esta trabalhando de verdade${Z}\n"
info "projeto lido: $PROJETO"
info "o agente escreve em works/<sessao>/ (sandbox). /sandbox off libera a pasta real."
info "Ctrl+C aqui encerra tudo"
echo
wait "$PID_WEB"
