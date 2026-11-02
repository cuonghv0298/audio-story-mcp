#!/usr/bin/env bash
# Chạy server VieNeu-TTS (API giống OpenAI) trên máy — CPU/ONNX trên Mac, GPU nếu có CUDA.
# Chép ý từ nova_culture_app/scripts/vieneu_mac.sh (29/10/2026), đổi venv/cổng cho repo này.
#   scripts/vieneu.sh setup   # tạo venv (lần đầu ~1–2 phút, weights tải từ HuggingFace lần chạy đầu)
#   scripts/vieneu.sh run     # http://127.0.0.1:$VIENEU_PORT (mặc định 8165), không watermark
# Biến môi trường: VIENEU_VENV (dùng lại venv có sẵn), VIENEU_PORT, VIENEU_API_KEY, VIENEU_WATERMARK (mặc định 0).
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION=3.8.3
VENV="${VIENEU_VENV:-${CLAUDE_PLUGIN_DATA:-$PWD/runs}/vieneu-venv}"
PORT="${VIENEU_PORT:-8165}"
setup() {
  [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c "import vieneu, apps.openai_speech" 2>/dev/null && return
  echo "→ cài VieNeu-TTS $VERSION vào $VENV …"
  uv venv -q "$VENV" --python 3.12
  # onnxruntime ≥ 1.31 từ chối weights trong cache HuggingFace (symlink) → ghim 1.22.1 (đo ở nova_culture_app 29/10)
  VIRTUAL_ENV="$VENV" uv pip install -q "vieneu==$VERSION" "onnxruntime==1.22.1" fastapi "uvicorn[standard]"
}
case "${1:-run}" in
  setup) setup ;;
  run)
    setup
    HOST=127.0.0.1 PORT="$PORT" VIENEU_WATERMARK="${VIENEU_WATERMARK:-0}" VIENEU_API_KEY="${VIENEU_API_KEY:-}" \
      exec "$VENV/bin/python" -m apps.openai_speech ;;
  *) echo "dùng: $0 setup|run" >&2; exit 2 ;;
esac
