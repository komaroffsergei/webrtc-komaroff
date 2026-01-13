#!/bin/sh

SETTINGS_JSON="{$( env | grep -E '^OTEL_|^FRONT_|^COM_GITLAB_CI_COMMIT_TIMESTAMP|^COM_GITLAB_CI_PIPELINE_IID|^COM_GITLAB_CI_COMMIT_BRANCH' | awk -F= '{gsub(/^FRONT_|^COM_GITLAB_CI_/, "", $1); printf "\"%s\":\"%s\",", $1, $2}' | sed 's/,$//')}"

sed -i "s#window.SETTINGS || {};#${SETTINGS_JSON};#" /usr/share/nginx/html/index.html

if [[ -n "$FRONT_PATH_PREFIX" ]]; then
  sed -i "s|\(src\|href\)=\"|\1=\"$FRONT_PATH_PREFIX|g" /usr/share/nginx/html/index.html
fi
