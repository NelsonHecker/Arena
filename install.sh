#!/bin/bash -i
set -e

export ARENA_REPO=${ARENA_REPO:-https://github.com/voshch/Arena.git}
export ARENA_BRANCH=${ARENA_BRANCH:-jazzy}
export ARENA_ROS_DISTRO=${ARENA_ROS_DISTRO:-jazzy}

read_default(){
    local prompt=$1
    local default=$2
    local result
    
    if [[ -t 0 ]]; then
        read -rp "$prompt [$default]: " result
        echo "${result:-$default}"
    else
        echo "$default"
    fi
}

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

docker build --progress=plain -t arena:dev -f src/Arena/_meta/docker/Dockerfile.dev . \
    --build-arg ROS_DISTRO="$ARENA_ROS_DISTRO" \
    --build-arg username="$(whoami)" \
    --build-arg group="$(id -gn)" \
    --build-arg uid="$(id -u)" \
    --build-arg gid="$(id -g)"

ln -rsf "$ARENA_WS_DIR/src/Arena/_meta/docker/source" ./arena
ln -rsf "$ARENA_WS_DIR/src/Arena/_meta/tools/Arena.code-workspace" ./ws-arena.code-workspace

echo 'Installed Arena'
echo 'run the following to get started:'
echo "  cd $ARENA_WS_DIR && source arena"