#!/usr/bin/env bash
# External probe for the live site. Usage: scripts/probe.sh <base-url>
# Prints one PASS/FAIL line per check and exits 1 if any check failed.
# shellcheck disable=SC2016  # jq programs are single-quoted on purpose
set -uo pipefail

MAX_COLLECT_AGE_HOURS=${PROBE_MAX_COLLECT_AGE_HOURS:-30}
MIN_SOURCES_OK_RATIO=${PROBE_MIN_SOURCES_OK_RATIO:-0.95}
MIN_POSTINGS=${PROBE_MIN_POSTINGS:-600}
MAX_REGISTER_AGE_DAYS=${PROBE_MAX_REGISTER_AGE_DAYS:-45}

base_url=${1:?usage: probe.sh <base-url>}
base_url=${base_url%/}
failed=0

fetch() {
  curl -fsS --retry 3 --retry-delay 20 --retry-all-errors --max-time 20 "$base_url$1"
}

report() { # report <name> <ok:0|1> <observed>
  if [[ $2 == 0 ]]; then
    echo "PASS $1: $3"
  else
    echo "FAIL $1: $3"
    failed=1
  fi
}

# Evaluates a jq program against the status body. The program must output
# "<ok> <observed>" where ok is true or false; any jq error is a failure.
check() { # check <name> <jq program>
  local out
  if [[ -z $status ]]; then
    report "$1" 1 "no /api/status body"
  elif out=$(jq -r \
      --argjson max_collect_h "$MAX_COLLECT_AGE_HOURS" \
      --argjson min_ratio "$MIN_SOURCES_OK_RATIO" \
      --argjson min_postings "$MIN_POSTINGS" \
      --argjson max_register_d "$MAX_REGISTER_AGE_DAYS" \
      'def epoch: sub("\\.[0-9]+"; "")
          | capture("^(?<t>.{19})(?<o>Z|[+-][0-9]{2}:[0-9]{2})$")
          | .o as $o
          | (.t + "Z" | fromdateiso8601)
            - (if $o == "Z" then 0
               else ($o[1:3] | tonumber) * 3600 + ($o[4:6] | tonumber) * 60
                    | if $o[0:1] == "+" then . else -. end end);
       '"$2" <<<"$status" 2>&1) && [[ $out == true\ * || $out == false\ * ]]; then
    report "$1" "$([[ $out == true\ * ]] && echo 0 || echo 1)" "${out#* }"
  else
    report "$1" 1 "invalid: ${out:-no output}"
  fi
}

if fetch /healthz >/dev/null; then
  report healthz 0 "200"
else
  report healthz 1 "request failed"
fi

status=$(fetch /api/status) || status=""

check "collection freshness" '
  ((now - (.last_collect_at | epoch)) / 3600) as $h
  | "\($h < $max_collect_h) \($h * 10 | floor / 10)h old (limit \($max_collect_h)h)"'

check "collection success" '
  .sources_ok as $ok | .sources_total as $total
  | if $total > 0 then
      "\($ok / $total >= $min_ratio) \($ok)/\($total) = \($ok / $total * 1000 | floor / 1000) (min \($min_ratio))"
    else "false \($ok)/\($total): no sources" end'

check "postings" '
  "\(.postings >= $min_postings) \(.postings) (min \($min_postings))"'

check "register freshness" '
  ((now - (.register_updated_on + "T00:00:00Z" | fromdateiso8601)) / 86400) as $d
  | "\($d < $max_register_d) \(.register_updated_on), \($d | floor) days old (limit \($max_register_d)d)"'

exit "$failed"
