#!/bin/sh
set -eu

# Usage: ./collect_file_contents.sh <output-file> <dir> [<dir>...]
# Collects every file under the supplied directories and records the path
# plus its contents into <output-file> as JSON objects with `path`/`content`.

if [ "$#" -lt 2 ]; then
  echo "Usage: $0 <output-file> <dir> [<dir>...]"
  exit 1
fi

output_file="$1"
shift

# Configure names or paths to skip. Plain names are treated as directory/file
# basenames matched everywhere. Entries containing `/`, `*`, `?`, or `[` act
# as path masks relative to the working directory.
DEFAULT_EXCLUDE_DIRS_FILES=$(cat <<'EOF'
.git
node_modules
dist
build
.qodo
.idea
.gitignore
README.md
third_party
model
models
.env.example
__pycache__
__init__
agents.md
#.gitlab-ci.yml
#.gitattributes
.venv
#.version
collect_file_contents.sh
src_lang_graph_1
src_lang_graph_2
src_core
src_front
src_llm
src_llm_test
src_llm_test_ruby
src_whisper
src_whisper_c
src_whisper_ruby
EOF
)
: "${EXCLUDE_DIRS_FILES:=$DEFAULT_EXCLUDE_DIRS_FILES}"
unset DEFAULT_EXCLUDE_DIRS_FILES

NAME_EXCLUDES=""
PATH_EXCLUDES=""
PATTERN_EXCLUDES=""
while IFS= read -r entry; do
  case "$entry" in
    ''|\#*)
      continue
      ;;
    *[\*\?\[]*)
      PATTERN_EXCLUDES="${PATTERN_EXCLUDES}${entry}
"
      ;;
    */*)
      PATH_EXCLUDES="${PATH_EXCLUDES}${entry}
"
      ;;
    *)
      NAME_EXCLUDES="${NAME_EXCLUDES}${entry}
"
      ;;
  esac
done <<EOF
$EXCLUDE_DIRS_FILES
EOF

prune_expr=""
while IFS= read -r excluded; do
  [ -z "$excluded" ] && continue
  if [ -z "$prune_expr" ]; then
    prune_expr="-name $excluded"
  else
    prune_expr="$prune_expr -o -name $excluded"
  fi
done <<EOF
$NAME_EXCLUDES
EOF

: > "$output_file"

process_tree() {
  dir="$1"
  if [ ! -d "$dir" ]; then
    printf 'Skipping %s: not a directory\n' "$dir" >&2
    return
  fi

  if [ -n "$prune_expr" ]; then
    find "$dir" -type d \( $prune_expr \) -prune -o -type f -print
  else
    find "$dir" -type f -print
  fi
}

should_skip_path() {
  target="$1"
  base=$(basename "$target")

  while IFS= read -r name_exclude; do
    [ -z "$name_exclude" ] && continue
    if [ "$base" = "$name_exclude" ]; then
      return 0
    fi
  done <<EOF
$NAME_EXCLUDES
EOF

  while IFS= read -r path_prefix; do
    [ -z "$path_prefix" ] && continue
    case "$target" in
      "$path_prefix"|"$path_prefix"/*)
        return 0
        ;;
    esac
  done <<EOF
$PATH_EXCLUDES
EOF

  while IFS= read -r pattern; do
    [ -z "$pattern" ] && continue
    case "$target" in
      $pattern)
        return 0
        ;;
    esac
  done <<EOF
$PATTERN_EXCLUDES
EOF

  return 1
}

json_entry() {
  src="$1"
  python3 -c '
import json, sys
path = sys.argv[1]
content = sys.stdin.buffer.read().decode("utf-8", "surrogateescape")
print(json.dumps({"path": path, "content": content}))
' "$src" < "$src"
}

for search_root in "$@"; do
  process_tree "$search_root" | while IFS= read -r current_file || [ -n "$current_file" ]; do
    if [ -z "$current_file" ]; then
      continue
    fi
    if should_skip_path "$current_file"; then
      continue
    fi
    json_entry "$current_file" >> "$output_file"
  done
done
