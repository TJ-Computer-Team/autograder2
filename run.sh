#!/bin/bash
set -e

if [ "$1" == "reset" ]; then
    echo "Resetting Docker containers and volumes..."
    sudo docker compose down -v
    rm -rf config/.first_log
else
    git submodule update --init --recursive
    sudo docker compose build  && sudo docker compose up
fi