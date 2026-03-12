#!/bin/bash

cd /opt/arena_ws
source source

if [ ! -f /.built ]; then
    echo "Running initial setup..."
    arena update
    BUILD_ALL=1 arena build
    sudo touch /.built
fi

exec "$@"