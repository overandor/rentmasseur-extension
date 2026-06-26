#!/bin/sh
if [ -f .env ]; then
    while IFS='=' read -r key value; do
        case "$key" in
            ''|\#*) continue ;;
        esac
        export "$key=$value"
    done < .env
fi
exec ./cpp_os_server 7860
