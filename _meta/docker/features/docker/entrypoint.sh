#!/bin/bash

export PYENV_ROOT="$HOME/.pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
command -v pyenv > /dev/null 2>&1 && eval "$(pyenv init - bash)"

if [ ! -f /.built ]; then
    exec 9> /tmp/arena-first-boot.lock
    if flock -n 9; then
        (
            set -e
            cd /opt/arena_ws
            source ./source
            _arena_venv_provision
            arena resource
            arena registry add docker
            echo "Running initial setup..."
            arena update
            rm -rf build/arena_models install/arena_models
            BUILD_ALL=1 arena build || true
            # --- Native Linux Blender 5.2.1 provisioning (arena blender build/render/animate) ---
            BLENDER_VERSION="5.2.1"
            BLENDER_TARBALL="/opt/arena_ws/.uv-cache/blender-${BLENDER_VERSION}-linux-x64.tar.xz"
            BLENDER_URL="https://download.blender.org/release/Blender5.2/blender-${BLENDER_VERSION}-linux-x64.tar.xz"
            if [ -x /opt/blender/blender ] && /opt/blender/blender --version 2>/dev/null | grep -qF "Blender ${BLENDER_VERSION}"; then
                echo "blender ${BLENDER_VERSION} already provisioned at /opt/blender/blender"
            else
                echo "Provisioning native Linux Blender ${BLENDER_VERSION}..."
                mkdir -p /opt/arena_ws/.uv-cache
                if ! tar -tJf "$BLENDER_TARBALL" >/dev/null 2>&1; then
                    # Tarball is cached in the bind-mounted .uv-cache so container
                    # recreation does not re-download (~1 GB); verify and re-fetch
                    # only if missing or corrupt.
                    echo "Downloading blender-${BLENDER_VERSION}-linux-x64.tar.xz..."
                    rm -f "$BLENDER_TARBALL"
                    curl -fsSL --retry 3 -o "$BLENDER_TARBALL" "$BLENDER_URL"
                fi
                sudo rm -rf /opt/blender
                sudo mkdir -p /opt/blender
                sudo tar -xJf "$BLENDER_TARBALL" -C /opt/blender --strip-components=1
                echo "blender provisioned: $(/opt/blender/blender --version 2>/dev/null | head -n 1)"
            fi
            # Drop the distro's apt Blender (4.x) so find_blender() resolves 5.2.1
            if dpkg -s blender >/dev/null 2>&1; then
                echo "Removing apt Blender ($(dpkg -s blender 2>/dev/null | grep -m1 '^Version'))..."
                sudo apt-get remove -y blender blender-data
                sudo apt-get autoremove -y --purge || true
            fi
            sudo touch /.built
            echo 'Initial setup complete.'
            echo -e '\033[0mRun \033[01;33marena feature docker commit\033[0m to save this state.'
        )
    elif [ -t 0 ]; then
        echo "arena: initial setup running in another session, shell is ready (docker logs -f for progress)"
    else
        flock 9
    fi
    exec 9>&-
fi

exec "$@"
