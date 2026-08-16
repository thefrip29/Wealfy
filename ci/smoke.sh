#!/usr/bin/env bash
# Lance l'application en mode serveur seul et verifie qu'elle repond.
#
# La suite de tests valide le CODE ; elle ne dit rien du paquet construit. Or
# c'est la que vivent les pannes d'empaquetage : une ressource non embarquee, un
# import que l'analyse statique a manque. Ce script exerce donc l'artefact
# lui-meme.
#
#   bash ci/smoke.sh python run.py                          # avant construction
#   bash ci/smoke.sh ./dist/Wealfy.exe                      # Windows
#   bash ci/smoke.sh ./dist/Wealfy.app/Contents/MacOS/Wealfy  # macOS
#
# Sur macOS on invoque le binaire INTERIEUR au bundle plutot que `open -a` :
# la sortie d'erreur reste alors attachee au terminal. C'est ce qui rend
# visible un « No module named objc », que --windowed masquerait autrement.
set -euo pipefail

PORT="${SMOKE_PORT:-5055}"
export PATRIMOINE_PORT="$PORT"

# Base jetable, JAMAIS celle du depot. Sans cela le test creerait une base a
# cote de l'executable, que app/paths.py prendrait ensuite pour un usage
# portable assume — et le lancement suivant lirait la mauvaise base.
TMPDIR_SMOKE="$(mktemp -d)"
export PATRIMOINE_DB="$TMPDIR_SMOKE/smoke.db"

nettoyer() {
  [ -n "${PID:-}" ] && kill "$PID" 2>/dev/null || true
  rm -rf "$TMPDIR_SMOKE"
}
trap nettoyer EXIT

echo "Lancement : $* --no-browser  (port $PORT)"
"$@" --no-browser &
PID=$!

for _ in $(seq 1 40); do
  # Le processus est-il encore vivant ? S'il est mort, inutile d'attendre :
  # c'est un echec au demarrage, et l'attente masquerait la vraie cause.
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "ECHEC : le processus s'est arrete avant de repondre." >&2
    wait "$PID" || true
    exit 1
  fi
  if reponse="$(curl -fsS "http://127.0.0.1:$PORT/api/meta" 2>/dev/null)"; then
    case "$reponse" in
      *asset_types*)
        echo "OK — /api/meta repond et contient asset_types"
        exit 0
        ;;
    esac
    echo "ECHEC : /api/meta a repondu sans asset_types." >&2
    exit 1
  fi
  sleep 0.5
done

echo "ECHEC : aucune reponse en 20 s." >&2
exit 1
