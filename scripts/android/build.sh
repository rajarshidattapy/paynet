#!/usr/bin/env bash
# Build the PayNet debug APK inside WSL. Run as your normal user (not root).
#
#   build.sh <wsl path to the repo>     e.g. build.sh /mnt/r/Paynet
#
# The project is copied into the Linux filesystem first: builds on /mnt/<drive>
# are very slow and trip over file permissions. The APK is copied back to
# <repo>/app/bin/.
set -euo pipefail

SRC="${1:?usage: build.sh <wsl path to the repo>}"
WORK="$HOME/paynet-build"

[ -f "$SRC/app/buildozer.spec" ] || { echo "no app/buildozer.spec under $SRC" >&2; exit 1; }
[ "$(id -u)" -ne 0 ] || { echo "run as a normal user, not root" >&2; exit 1; }

# --- Python 3.11 toolchain (the distro Python may be too new for buildozer) --
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null; then
  # Official uv installer (https://docs.astral.sh/uv/).
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
VENV="$HOME/buildozer-venv"
[ -x "$VENV/bin/python" ] || uv venv --python 3.11 "$VENV"
# uv venvs ship without pip, but buildozer shells out to `python -m pip`.
uv pip install --python "$VENV/bin/python" pip buildozer "cython<3" setuptools
# Same as `activate`. VIRTUAL_ENV matters: without it buildozer adds
# `pip install --user`, which pip refuses inside a venv.
export VIRTUAL_ENV="$VENV"
export PATH="$VENV/bin:$PATH"

# --- sync the project (keeps .buildozer and bin so rebuilds are incremental) -
mkdir -p "$WORK/app"
rsync -a --delete \
  --exclude '.buildozer/' --exclude 'bin/' --exclude '__pycache__/' \
  --exclude '.pytest_cache/' --exclude '.venv/' --exclude 'snapshot_failures/' \
  "$SRC/app/" "$WORK/app/"

# --- build -------------------------------------------------------------------
cd "$WORK/app"
buildozer -v android debug

# --- hand the APK back to Windows -------------------------------------------
mkdir -p "$SRC/app/bin"
cp -v bin/*.apk "$SRC/app/bin/"
echo "build: done"
