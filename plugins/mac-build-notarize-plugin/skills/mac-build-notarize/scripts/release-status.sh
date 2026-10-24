#!/bin/bash
# -----------------------------------------------------------------------------
# release-status.sh: writes a machine-readable view of a release run to
# $BUILD_DIR/release-status.json at every stage boundary. The release-pane
# Claude Code plugin reads that file and shows the stages in a pane.
#
# Source it from build-and-notarize.sh after these are set:
#   APP_NAME, PROJECT_DIR, BUILD_DIR, DRY_RUN (true/false)
#   STAGE_IDS     ids, one per stage, in order (e.g. archive, export, dmg)
#   STAGE_TITLES  a title for each id, same order
#   DRY_RUN_SKIPPED_STAGES  ids a --dry-run never reaches (may be empty)
#
# Then:
#   stage <id>          marks the running stage done and starts <id>
#   stage_note "<text>" a short note on the running stage
#   write_status        rewrites the file (after setting VERSION, DMG_PATH,
#                       RUN_WAITING, ...)
# and in the script's error() helper, set RUN_ERROR="$1" before exiting.
#
# It installs an EXIT trap that marks the running stage done or failed, so the
# calling script must not set an EXIT trap of its own.
#
# A stage whose id matches a log file in $BUILD_DIR (archive -> archive.log)
# points to that log, which the pane shows when the stage fails.
#
# ASCII only: bash can read non-ASCII characters next to a $VARIABLE as part
# of its name.
# -----------------------------------------------------------------------------

STATUS_FILE="$BUILD_DIR/release-status.json"
STAGE_STATES=()
STAGE_STARTS=()
STAGE_ENDS=()
STAGE_NOTES=()
for i in "${!STAGE_IDS[@]}"; do
    STAGE_STATES[i]="pending"
    STAGE_STARTS[i]=""
    STAGE_ENDS[i]=""
    STAGE_NOTES[i]=""
    if [ "$DRY_RUN" = true ]; then
        for skipped in ${DRY_RUN_SKIPPED_STAGES[@]+"${DRY_RUN_SKIPPED_STAGES[@]}"}; do
            if [ "$skipped" = "${STAGE_IDS[i]}" ]; then
                STAGE_STATES[i]="skipped"
                STAGE_NOTES[i]="dry run"
            fi
        done
    fi
done
CURRENT_STAGE=-1
RUN_ID="$(date +%s)-$$"
RUN_STARTED=$(date +%s)
RUN_ENDED=""
RUN_STATE="running"
RUN_ERROR=""
RUN_WAITING=""
VERSION="${VERSION:-}"
DMG_PATH="${DMG_PATH:-}"

json_string() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\n'/\\n}"
    s="${s//$'\r'/}"
    s="${s//$'\t'/\\t}"
    printf '"%s"' "$s"
}

json_number_or_null() {
    if [ -n "$1" ]; then printf '%s' "$1"; else printf 'null'; fi
}

write_status() {
    [ -d "$BUILD_DIR" ] || return 0
    local dmg_size=""
    if [ -n "$DMG_PATH" ] && [ -f "$DMG_PATH" ]; then
        dmg_size=$(stat -f %z "$DMG_PATH" 2>/dev/null || true)
    fi
    {
        printf '{\n'
        printf '  "runId": %s,\n' "$(json_string "$RUN_ID")"
        printf '  "appName": %s,\n' "$(json_string "$APP_NAME")"
        printf '  "projectDir": %s,\n' "$(json_string "$PROJECT_DIR")"
        printf '  "dryRun": %s,\n' "$DRY_RUN"
        printf '  "state": %s,\n' "$(json_string "$RUN_STATE")"
        printf '  "startedAt": %s,\n' "$RUN_STARTED"
        printf '  "endedAt": %s,\n' "$(json_number_or_null "$RUN_ENDED")"
        printf '  "updatedAt": %s,\n' "$(date +%s)"
        printf '  "version": %s,\n' "$(json_string "$VERSION")"
        printf '  "dmgPath": %s,\n' "$(json_string "$DMG_PATH")"
        printf '  "dmgSize": %s,\n' "$(json_number_or_null "$dmg_size")"
        printf '  "waiting": %s,\n' "$(json_string "$RUN_WAITING")"
        printf '  "error": %s,\n' "$(json_string "$RUN_ERROR")"
        printf '  "stages": [\n'
        local i last=$((${#STAGE_IDS[@]} - 1)) log
        for i in "${!STAGE_IDS[@]}"; do
            log="$BUILD_DIR/${STAGE_IDS[i]}.log"
            [ -f "$log" ] || log=""
            printf '    {"id": %s, "title": %s, "state": %s, "startedAt": %s, "endedAt": %s, "note": %s, "log": %s}' \
                "$(json_string "${STAGE_IDS[i]}")" \
                "$(json_string "${STAGE_TITLES[i]}")" \
                "$(json_string "${STAGE_STATES[i]}")" \
                "$(json_number_or_null "${STAGE_STARTS[i]}")" \
                "$(json_number_or_null "${STAGE_ENDS[i]}")" \
                "$(json_string "${STAGE_NOTES[i]}")" \
                "$(json_string "$log")"
            [ "$i" -lt "$last" ] && printf ','
            printf '\n'
        done
        printf '  ]\n'
        printf '}\n'
    } > "$STATUS_FILE.tmp" 2>/dev/null && mv -f "$STATUS_FILE.tmp" "$STATUS_FILE" 2>/dev/null || true
}

# Marks the running stage done and starts stage $1 (an id from STAGE_IDS).
stage() {
    local i
    if [ "$CURRENT_STAGE" -ge 0 ] && [ "${STAGE_STATES[CURRENT_STAGE]}" = "running" ]; then
        STAGE_STATES[CURRENT_STAGE]="done"
        STAGE_ENDS[CURRENT_STAGE]=$(date +%s)
    fi
    for i in "${!STAGE_IDS[@]}"; do
        if [ "${STAGE_IDS[i]}" = "$1" ]; then
            CURRENT_STAGE=$i
            STAGE_STATES[i]="running"
            STAGE_STARTS[i]=$(date +%s)
            STAGE_ENDS[i]=""
        fi
    done
    write_status
}

stage_note() {
    [ "$CURRENT_STAGE" -ge 0 ] && STAGE_NOTES[CURRENT_STAGE]="$1"
    write_status
}

release_status_on_exit() {
    local code=$?
    RUN_ENDED=$(date +%s)
    RUN_WAITING=""
    if [ "$CURRENT_STAGE" -ge 0 ] && [ "${STAGE_STATES[CURRENT_STAGE]}" = "running" ]; then
        STAGE_ENDS[CURRENT_STAGE]=$RUN_ENDED
        if [ "$code" -eq 0 ]; then
            STAGE_STATES[CURRENT_STAGE]="done"
        else
            STAGE_STATES[CURRENT_STAGE]="failed"
        fi
    fi
    if [ "$code" -eq 0 ]; then
        RUN_STATE="done"
    else
        RUN_STATE="failed"
        [ -n "$RUN_ERROR" ] || RUN_ERROR="Exited with status $code."
    fi
    write_status
}
trap release_status_on_exit EXIT
