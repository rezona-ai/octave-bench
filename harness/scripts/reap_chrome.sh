#!/bin/bash
# kill orphaned / runaway headless browsers left behind by agent self-tests
n=0
for p in $(pgrep -f "chrome|chromium"); do
  pp=$(ps -o ppid= -p $p 2>/dev/null | tr -d " "); et=$(ps -o etimes= -p $p 2>/dev/null | tr -d " ")
  [ -z "$et" ] && continue
  if [ "$pp" = "1" ] || [ "$et" -gt 1800 ]; then kill -9 $p 2>/dev/null && n=$((n+1)); fi
done
echo "$(date +%F_%T) reaped $n" >> /var/log/reap_chrome.log
