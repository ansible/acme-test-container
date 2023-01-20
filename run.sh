#!/bin/sh
set -e
# Our internal BIND (started by Controller) is the official DNS resolver for this container
echo nameserver 127.0.0.1 > /etc/resolv.conf
# Make Pebble sleep at most 5 seconds between auth checks (default is 15 seconds)
export PEBBLE_VA_SLEEPTIME=5
# Add three alternate roots with intermediate certs
export PEBBLE_ALTERNATE_ROOTS=3
# Start controller in background
export CONTROLLER_PORT=5000
export GOPATH=/go
/usr/local/bin/python /root/controller.py &
# Create Pebble config
/usr/local/bin/python /root/create-pebble-config.py /pebble-src/test/config/pebble-config.json
# Start Pebble
cd /pebble-src
/go/bin/pebble -config /pebble-src/test/config/pebble-config.json -strict true
