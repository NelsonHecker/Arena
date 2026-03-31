#!/bin/bash

source ~/.bashrc

export PYENV_ROOT="$HOME/.pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init - bash)"

set -e
cd /opt/arena_ws
source source

if [ ! -f /.built ]; then
    echo "Running initial setup..."
    arena update
    rm -r build/arena_models install/arena_models || true
    BUILD_ALL=1 arena build || true
    sudo touch /.built
    echo 'Initial setup complete.'
    echo -e '\033[0mRun \033[01;33marena feature docker commit\033[0m to save this state.'
fi

set +e

exec "$@"