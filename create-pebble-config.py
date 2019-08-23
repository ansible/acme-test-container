#!/usr/bin/env python
# -*- coding: utf-8 -*-
# (c) 2019 Felix Fontein (@felixfontein) <felix@fontein.de>
#
# Written by Felix Fontein <felix@fontein.de>
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

import json
import socket
import sys

own_ip = socket.gethostbyname(socket.gethostname())

config = {
  "pebble": {
    "listenAddress": "0.0.0.0:14000",
    "managementListenAddress": "0.0.0.0:15000",
    "certificate": "test/certs/localhost/cert.pem",
    "privateKey": "test/certs/localhost/key.pem",
    "httpPort": 5000,
    "tlsPort": 5001,
    "ocspResponderURL": "http://{0}:6000".format(own_ip),  # will be added later
  }
}

with open(sys.argv[1], "wt") as f:
    f.write(json.dumps(config))
