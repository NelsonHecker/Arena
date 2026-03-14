#!/bin/bash


set -e
cd /opt/arena_ws
source source

if [ ! -f /.built ]; then
    echo "Running initial setup..."
    arena update
    BUILD_ALL=1 arena build || true
    sudo touch /.built
    echo 'Initial setup complete.'
    echo -e 'Run \033[01;33marena feature docker commit\033[0m to cache this state.'
fi

set +e

exec "$@"