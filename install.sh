#!/bin/bash -i
set -e

export ARENA_REPO=${ARENA_REPO:-https://github.com/voshch/Arena.git}
export ARENA_BRANCH=${ARENA_BRANCH:-jazzy}

# == read inputs ==
echo 'Configuring Arena...'

ARENA_WS_DIR=$(realpath "$(eval echo "$(read_default "Arena workspace directory" "${ARENA_WS_DIR:-~/arena_ws}")")")
export ARENA_WS_DIR

echo "installing ${ARENA_REPO}:${ARENA_BRANCH} on ROS2 ${ARENA_ROS_DISTRO} to $ARENA_WS_DIR"
sudo echo 'confirmed'
mkdir -p "$ARENA_WS_DIR"
cd "$ARENA_WS_DIR"

# set up
mkdir -p src
if [ ! -d src/Arena ]; then
    git clone "$ARENA_REPO" -b "$ARENA_BRANCH" src/Arena
fi

docker build --progress=plain -t arena -f src/Arena/_meta/docker/Dockerfile . 