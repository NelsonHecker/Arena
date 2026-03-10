#!/bin/bash -i

install(){
    cd "$ARENA_DIR"

    # Initialize arena_training submodules (rosnav_rl)
    echo "Initializing arena_training submodules..."
    if [ -d "$ARENA_DIR/arena_training" ]; then
        pushd "$ARENA_DIR/arena_training" > /dev/null
        git submodule update --init --recursive
        popd > /dev/null
    fi

    # Install Python training dependencies via uv
    echo "Installing training Python dependencies..."
    uv sync --inexact --group training

    # Rebuild the workspace to compile rosnav_rl C++ plugin and install Python packages
    echo "Building rosnav_rl and arena_training packages..."
    cd "$ARENA_WS_DIR"
    arena build
    
    echo ""
    echo "=== Training feature installed successfully ==="
    echo ""
    echo "Usage:"
    echo "  Train:   [without simulation] ros2 run arena_training train_agent.py --config sb_training_config.yaml"
    echo "  Train:   arena launch sim:=gazebo local_planner:=rosnav_rl env_n:=2 train_config:=<path to config.yaml>"
    echo "  Deploy:  arena launch local_planner:=rosnav_rl agent_name:=<your_agent>"
    echo ""
}

uninstall(){
    echo "To uninstall training support, remove the arena_training package"
    echo "and rebuild the workspace."
    echo "  rm -rf $ARENA_DIR/arena_training"
    echo "  arena build"
}

# === MAIN SCRIPT ===
help(){
    echo "Usage: training.sh <install|uninstall>"
    echo ""
    echo "Installs arena_training and rosnav_rl for DRL-based navigation."
    echo "This enables:"
    echo "  - Training RL agents with Stable Baselines 3"
    echo "  - Deploying trained agents as nav2 local planners"
    echo "  - Action server for real-time model inference"
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
    *)
        help
        exit 1
    ;;
esac
