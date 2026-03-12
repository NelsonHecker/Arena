#!/usr/bin/env bash

docker_env=(
    ARENA_IMAGE="$ARENA_IMAGE"
    ARENA_WS_DIR="$ARENA_WS_DIR"
)
export docker_env

docker_update(){
    sudo ${docker_env[*]} \
        docker compose \
        -f "$ARENA_DIR/_meta/docker/docker-compose.yaml" \
        --project-directory "$ARENA_WS_DIR" \
        build \
        arena
}

docker_commit(){
    CONTAINER_ID=$(sudo ${docker_env[*]} \
        docker compose \
        -f "$ARENA_DIR/_meta/docker/docker-compose.yaml" \
        --project-directory "$ARENA_WS_DIR" \
        --project-name "$PROJECT_NAME" \
        ps -q -a arena \
        | tail -n 1)
    echo "committing container to image $ARENA_IMAGE..."
    sudo ${docker_env[*]} docker commit "$CONTAINER_ID" "$ARENA_IMAGE"
    echo "done"
}

# === MAIN SCRIPT ===
help(){
    echo "Usage: arena feature docker <update|commit>"
}

if [ $# -ne 1 ]; then
    help
    exit 1
fi
case "$1" in
    update)
        docker_update
    ;;
    commit)
        docker_commit
    ;;
    *)
        help
        exit 1
    ;;
esac
