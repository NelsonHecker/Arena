#!/bin/bash -i

#!/bin/bash -i


name="isaac"

install(){
    set -e

    pushd "$ARENA_DIR" > /dev/null
        git submodule update --init arena_isaac
    popd > /dev/null
    
    if ! grep -q "$name" "$INSTALLED" 2>/dev/null; then
        echo "$name" >> "$INSTALLED"
    fi

    arena update
    arena build

    echo "Installed $name successfully."
}

uninstall(){
    #TODO
    echo not implemented, but unsetting flag
    pushd "$ARENA_DIR" > /dev/null
        git submodule deinit -f arena_isaac
    popd > /dev/null
    sed -i "/$name/d" "$INSTALLED"
}

source_fn(){
    if [[ ! "$ARENA_MODELS_FORMATS" =~ usd ]]; then
        export ARENA_MODELS_FORMATS="${ARENA_MODELS_FORMATS},usdz,usd,usda,usdc"
    fi
}

launch(){
    docker compose \
        -f "$ARENA_DIR/_meta/docker/docker-compose.yaml" \
        --project-directory "$ARENA_WS_DIR" \
        --project-name "$PROJECT_NAME" \
        up --remove-orphans isaac
}

# === MAIN SCRIPT ===
help(){
    echo "Usage: $name <install|uninstall|source|launch>"
}
if [ $# -ne 1 ]; then
    help
    exit 1
fi
case "$1" in
    install)
        install
    ;;
    uninstall)
        uninstall
    ;;
    source)
        source_fn
    ;;
    launch)
        echo 'not implemented yet'
        exit 1
    ;;
    *)
        help
        exit 1
    ;;
esac
