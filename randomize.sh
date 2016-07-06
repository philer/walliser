#!/bin/zsh
# set -e

update_wallpapers() {
    feh --bg-fill --no-fehbg "$current_wallpapers[@]"
}
die() {
    echo "$@" >&2; exit 1
}

## input ##

(( $# > 1 )) || die "need input"

if [[ "$1" =~ ^[0-9]+(\.[0-9]+)?[smhd]?$ ]]; then
    bg_update_interval="$1"
    shift
    (( $# > 1 )) || die "need input"
else
    bg_update_interval=${bg_update_interval:-10s}
fi

wallpapers=($(find $(readlink -e $@) -type f))

echo "Found ${#wallpapers} wallpapers." >&2

## init ##

monitors=$(xrandr -q | grep --count " connected ")

current_wallpapers=()
next_monitor=0

random_loop() {
    local next_wallpaper=""
    
    # init
    if [ -z "$current_wallpapers" ]; then
        echo "Setting initial wallpapers:" >&2
        
        for (( i=0 ; i<$monitors ; i++)); do
            next_wallpaper="${wallpapers[ $(( $RANDOM % ${#wallpapers} )) ]}"
            echo "file://$next_wallpaper"
            current_wallpapers+=("$next_wallpaper")
        done
        update_wallpapers
    fi
    
    # run loop
    while true; do
        sleep $bg_update_interval
        next_wallpaper="${wallpapers[ $(( $RANDOM % ${#wallpapers} )) ]}"
        
        echo "Updating wallpaper for monitor $next_monitor:" >&2
        echo "file://$next_wallpaper"
        # convert "$next_wallpaper" -print "%wx%h\n" /dev/null >&2
        
        current_wallpapers[$(( $next_monitor + 1 ))]="$next_wallpaper"
        update_wallpapers
        next_monitor=$(( ($next_monitor+1) % $monitors ))
    done
}

ordered_loop() {
    local current_id=0
    local next_wallpaper=""
    
    if [ -z "$current_wallpapers" ]; then
        echo "Setting initial wallpapers:" >&2
        current_wallpapers=($wallpapers[1,$monitors])
        for wp in $current_wallpapers; do echo "file://$wp"; done
        update_wallpapers
        current_id=$monitors
    fi
    
    while true; do
        sleep $bg_update_interval
        current_id=$(( ($current_id+1) % ${#wallpapers} ))
        next_wallpaper="${wallpapers[ $current_id ]}"
        
        echo "Updating wallpaper for monitor $next_monitor:" >&2
        echo "file://$next_wallpaper"
        # convert "$next_wallpaper" -print "%wx%h\n" /dev/null >&2
        
        current_wallpapers[$(( $next_monitor + 1 ))]="$next_wallpaper"
        update_wallpapers
        next_monitor=$(( ($next_monitor+1) % $monitors ))
    done
}

shuffled_loop() {
    wallpapers=($(shuf -e $wallpapers))
    ordered_loop
}

sorted_loop() {
    wallpapers=($(for wp in "${wallpapers[@]}"; do echo "$wp"; done | sort))
    ordered_loop
}

# random_loop
# ordered_loop
shuffled_loop
# sorted_loop
