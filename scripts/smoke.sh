#!/usr/bin/env bash
# Prueba de humo de punta a punta: datos + API + Streamlit (sin navegador).
# Uso: ./scripts/smoke.sh   (usa el puerto 8001 para no chocar con tu API en 8000)
# Tras cambiar de dominio, ajusta PREDICT_BODY a los campos de /optimizar.
set -u
cd "$(dirname "$0")/.."
PY=.venv/bin/python
PORT=${PORT:-8001}
API="http://localhost:$PORT"
PREDICT_BODY='{"presupuesto":500000}'
FALLOS=0
ok()  { echo "  ✅ $1"; }
mal() { echo "  ❌ $1"; FALLOS=$((FALLOS + 1)); }

echo "1) Datos"
[ -f data/candidatos.csv ] || $PY data/generate.py >/dev/null
[ -f data/candidatos.csv ] && ok "data/celdas.csv ($(wc -l < data/celdas.csv | tr -d ' ') líneas)" || mal "faltan datos: python data/generate.py"

echo "2) API en $API"
LOG=$(mktemp)
.venv/bin/uvicorn app.main:app --port "$PORT" >"$LOG" 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null; rm -f "$LOG"' EXIT
for _ in $(seq 1 60); do  # espera hasta 30 s a que entrene el modelo
  curl -sf "$API/health" >/dev/null && break
  kill -0 $PID 2>/dev/null || break
  $PY -c "import time; time.sleep(0.5)"
done
if ! curl -sf "$API/health" >/dev/null; then
  mal "la API no arranca. Log:"; tail -20 "$LOG"; exit 1
fi
ok "/health  $(curl -s "$API/health" | head -c 120)"

BODY=$(curl -s -w '\n%{http_code}' -X POST "$API/optimizar" -H 'Content-Type: application/json' -d "$PREDICT_BODY")
CODE=${BODY##*$'\n'}; BODY=${BODY%$'\n'*}
if [ "$CODE" = 200 ]; then
  ok "/optimizar  $(echo "$BODY" | head -c 150)…"
  echo "     fuente de la explicación: $(echo "$BODY" | $PY -c "import sys,json; print(json.load(sys.stdin)['explicacion']['fuente'])")  (llm = Claude; plantilla = fallback)"
else
  mal "/optimizar HTTP $CODE: $BODY"
fi
for p in /ciudad /diagnostico /parque/0; do
  C=$(curl -s -o /dev/null -w '%{http_code}' "$API$p")
  [ "$C" = 200 ] && ok "$p" || mal "$p HTTP $C"
done

echo "3) Streamlit (AppTest)"
MSG=$(API_URL=$API $PY - 2>/dev/null <<'EOF'
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("frontend/streamlit_app.py", default_timeout=60).run()
if at.button:
    at.button[0].click().run()  # pulsa el botón principal (Predecir)
problemas = [e.value for e in at.exception] + [e.value for e in at.error]
print(" | ".join(map(str, problemas)) if problemas else "OK")
EOF
)
[ "$MSG" = OK ] && ok "carga todas las pestañas y el botón principal funciona" || mal "Streamlit: ${MSG:-no se pudo ejecutar}"

echo
[ $FALLOS = 0 ] && echo "TODO OK ✅" || echo "$FALLOS FALLO(S) ❌"
exit $FALLOS
