#!/usr/bin/env bash
# One-time system setup for building the PayNet APK inside WSL (Ubuntu).
# Run as root; build-and-install.ps1 does this for you with `wsl -u root`.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
apt-get update

# Packages from the buildozer docs, plus a compiler toolchain for the host
# Python build and rsync for syncing the project in.
apt-get install -y \
  git zip unzip curl rsync build-essential ccache autoconf libtool pkg-config \
  zlib1g-dev libncurses-dev cmake libffi-dev libssl-dev

# python-for-android's Gradle build wants JDK 17; fall back to 21 if the
# distro no longer ships 17.
apt-get install -y openjdk-17-jdk || apt-get install -y openjdk-21-jdk

java -version
echo "setup-wsl: done"
