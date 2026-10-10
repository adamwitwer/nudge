#!/bin/sh
# Power-outage watcher. Runs on a Mac with a UPS on USB (here: the Plex-Mini),
# not on the Pi: the Pi is on its own UPS and never notices an outage.
#
# macOS reads the UPS itself, and `pmset -g pslog` prints a line the moment
# the power source changes. When it switches to the UPS, ask nudge on the Pi
# to send a reminder. Tested 2026-10-10 with a CyberPower CP850PFCLCD: a 10 s
# and a 2 s pull of the wall plug were both reported.
#
# Install: see outage/nudge.outage-watch.plist.

PI="adam@100.107.81.122"  # the machine running `nudge run` (Tailscale)
DETAIL="reset the clocks, gaming PC, and plant lamp timers"
COOLDOWN=1800             # one nudge per 30 min, however much the power flickers

notify() {
    cmd="cd ~/Projects/nudge && venv/bin/python -m nudge send 'Power outage at $1' --detail '$DETAIL' --emoji ⚡ --quiet"
    for attempt in 1 2 3 4 5; do
        # -n: otherwise ssh swallows the pmset lines the loop below is reading
        ssh -n -o BatchMode=yes -o ConnectTimeout=10 "$PI" "$cmd" && return 0
        sleep 60
    done
    echo "$(date '+%F %T') gave up telling the Pi"
    return 1
}

last=0
pmset -g pslog | while IFS= read -r line; do
    case "$line" in
        *"Now drawing from 'UPS Power'"*) ;;
        *) continue ;;
    esac
    echo "$(date '+%F %T') on UPS power"
    now=$(date +%s)
    [ $((now - last)) -lt "$COOLDOWN" ] && continue
    last=$now
    notify "$(date '+%-I:%M %p')"
done
