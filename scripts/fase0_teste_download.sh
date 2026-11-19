#!/usr/bin/env bash
# FASE 0: baixa um trecho de um VOD e reporta tamanho, duração e bloqueio de IP.
# Uso: fase0_teste_download.sh <url> <inicio_seg> <duracao_seg>
set -uo pipefail

URL="$1"; INICIO="${2:-0}"; DURACAO="${3:-600}"
FIM=$((INICIO + DURACAO))
OUT=trabalho/fase0
mkdir -p "$OUT"
RESUMO="${GITHUB_STEP_SUMMARY:-/dev/stdout}"
LOG="$OUT/download.log"
: > "$LOG"

echo "IP público do runner: $(curl -s https://api.ipify.org || echo desconhecido)" | tee -a "$LOG"

tenta_ytdlp() {
  yt-dlp --no-playlist --newline \
    --download-sections "*${INICIO}-${FIM}" \
    -f "best[height<=720]/bestvideo[height<=720]+bestaudio/best" \
    --merge-output-format mp4 \
    -o "$OUT/trecho.%(ext)s" "$URL" 2>&1 | tee -a "$LOG"
  return "${PIPESTATUS[0]}"
}

tenta_twitchdl() {
  twitch-dl download "$URL" --start "$INICIO" --end "$FIM" -q 720p \
    -o "$OUT/trecho.mkv" --overwrite 2>&1 | tee -a "$LOG"
  return "${PIPESTATUS[0]}"
}

METODO="yt-dlp"
tenta_ytdlp; RC=$?
if [ $RC -ne 0 ] && [[ "$URL" == *twitch.tv* ]]; then
  echo ">> yt-dlp falhou (rc=$RC), tentando twitch-dl..." | tee -a "$LOG"
  METODO="twitch-dl"
  tenta_twitchdl; RC=$?
fi

BLOQUEIO="não detectado"
if grep -qiE "HTTP Error (403|429)|Forbidden|Too Many Requests|Sign in to confirm|not a bot|captcha|geo.?restrict|unavailable in your country" "$LOG"; then
  BLOQUEIO="SIM — padrão de bloqueio/limite encontrado no log"
fi

ARQ=$(ls "$OUT"/trecho.* 2>/dev/null | head -n1 || true)
{
  echo "## Fase 0 — teste de download"
  echo "- URL: \`$URL\`"
  echo "- Trecho pedido: ${INICIO}s a ${FIM}s"
  echo "- Método: $METODO (código de saída: $RC)"
  echo "- Bloqueio de IP do runner: **$BLOQUEIO**"
  if [ -n "$ARQ" ] && [ -s "$ARQ" ]; then
    TAM=$(du -h "$ARQ" | cut -f1)
    DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$ARQ" 2>/dev/null || echo "?")
    RES=$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate -of csv=p=0 "$ARQ" 2>/dev/null || echo "?")
    echo "- Arquivo: \`$(basename "$ARQ")\`"
    echo "- Tamanho: **$TAM**"
    echo "- Duração: **${DUR}s** (esperado ~${DURACAO}s)"
    echo "- Resolução/fps: $RES"
    echo "- Resultado: ✅ download OK"
  else
    echo "- Resultado: ❌ nenhum arquivo gerado"
    echo ""
    echo "Últimas linhas do log:"
    echo '```'
    tail -n 15 "$LOG"
    echo '```'
  fi
} | tee -a "$RESUMO"

# Descarta o vídeo para não deixar nada vazar; só o log vai como artefato.
rm -f "$OUT"/trecho.*
[ $RC -eq 0 ]
