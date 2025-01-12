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
    "retryAfter": {
        "authz": 1,
        "order": 1,
    },
    "ocspResponderURL": "http://{0}:5000/ocsp".format(own_ip),  # will be added later
    "externalAccountBindingRequired": False,
    "externalAccountMACKeys": {
      "kid-1": "zWNDZM6eQGHWpSRTPal5eIUYFTu7EajVIoguysqZ9wG44nMEtx3MUAsUDkMTQ12W",
      "kid-2": "b10lLJs8l1GPIzsLP0s6pMt8O0XVGnfTaCeROxQM0BIt2XrJMDHJZBM5NuQmQJQH",
      "kid-3": "zWNDZM6eQGHWpSRTPal5eIUYFTu7EajVIoguysqZ9wG44nMEtx3MUAsUDkMTQ12W",
      "kid-4": "b10lLJs8l1GPIzsLP0s6pMt8O0XVGnfTaCeROxQM0BIt2XrJMDHJZBM5NuQmQJQH",
      "kid-5": "zWNDZM6eQGHWpSRTPal5eIUYFTu7EajVIoguysqZ9wG44nMEtx3MUAsUDkMTQ12W",
      "kid-6": "b10lLJs8l1GPIzsLP0s6pMt8O0XVGnfTaCeROxQM0BIt2XrJMDHJZBM5NuQmQJQH",
      "kid-7": "HjudV5qnbreN-n9WyFSH-t4HXuEx_XFen45zuxY-G1h6fr74V3cUM_dVlwQZBWmc",
    },
    "domainBlocklist": ["blocked-domain.example"],
    "profiles": {
      "default": {
        "description": "The profile you know and love",
        "validityPeriod": 7776000,
      },
      "shortlived": {
        "description": "A short-lived cert profile, without actual enforcement",
        "validityPeriod": 518400,
      },
    },
  },
}

with open(sys.argv[1], "wt") as f:
    f.write(json.dumps(config))
