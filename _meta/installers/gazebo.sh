#!/bin/bash -i
set -e

name="gazebo"

install(){
  # Define Arena workspace directory
  cd "$ARENA_WS_DIR"

  # Install dependencies
  sudo apt-get update
  sudo apt-get install -y \
    ros-$ARENA_ROS_DISTRO-ros-gz-sim \
    ros-$ARENA_ROS_DISTRO-ros-gz-bridge \
    ros-$ARENA_ROS_DISTRO-ros-gz-image

  echo "Gazebo ${GAZEBO_VERSION}, ros_gz, sdformat_urdf installed successfully!"


  export USD_PATH="$ARENA_WS_DIR/tools/OpenUSD/install"

  if [ ! -d tools/OpenUSD ]; then
    echo "Installing OpenUSD"
    mkdir -p tools
    pushd tools
      git clone --depth 1 -b v24.08 https://github.com/PixarAnimationStudios/OpenUSD.git
      sudo apt-get install -y libpyside2-dev python3-opengl cmake libglu1-mesa-dev freeglut3-dev mesa-common-dev
      cd OpenUSD
      python3 build_scripts/build_usd.py --build-variant release --no-tests --no-examples --no-imaging --onetbb --no-tutorials --no-docs --no-python "$USD_PATH"
    popd
  fi

  export PATH=$USD_PATH/bin:$PATH
  export LD_LIBRARY_PATH=$USD_PATH/lib:$LD_LIBRARY_PATH
  export CMAKE_PREFIX_PATH=$USD_PATH:$CMAKE_PREFIX_PATH

  if [ ! -d src/tools/gz-usd ]; then
    echo "Installing gz-usd"
    sudo apt-get install -y libgz-cmake4-dev libsdformat15-dev libgz-common6-dev
    mkdir -p src/tools
    pushd src/tools
      git clone -b main https://github.com/gazebosim/gz-usd
    popd
    BASE_PATHS=src/tools/gz-usd arena build
    echo "Successfully installed gz-usd"
  fi

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
  sed -i "/$name/d" "$INSTALLED"
}

# === MAIN SCRIPT ===
help(){
  echo "Usage: gazebo.sh <install|uninstall>"
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