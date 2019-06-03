# -*- coding: utf-8 -*-
# Copyright 2015 Electronic Frontier Foundation and others
# Modified 2018 by Felix Fontein <felix@fontein.de>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import binascii
import os
import socket
import socketserver
import threading

from OpenSSL import crypto
from OpenSSL import SSL


class _DefaultCertSelection(object):
    def __init__(self, certs):
        self.certs = certs

    def __call__(self, connection):
        server_name = connection.get_servername()
        return self.certs.get(server_name, None)


class SSLSocket(object):
    """SSL wrapper for sockets.

    :ivar socket sock: Original wrapped socket.
    :ivar dict certs: Mapping from domain names (`bytes`) to
        `OpenSSL.crypto.X509`.
    :ivar alpn_selection: Hook to select negotiated ALPN protocol for
        connection.
    :ivar cert_selection: Hook to select certificate for connection. If given,
        `certs` parameter would be ignored, and therefore must be empty.

    """
    def __init__(self, sock, log_callback, certs=None, alpn_selection=None, cert_selection=None):
        self.sock = sock
        self.log_callback = log_callback
        self.alpn_selection = alpn_selection
        self.method = SSL.SSLv23_METHOD
        if not cert_selection and not certs:
            raise ValueError("Neither cert_selection or certs specified.")
        if cert_selection and certs:
            raise ValueError("Both cert_selection and certs specified.")
        if cert_selection is None:
            cert_selection = _DefaultCertSelection(certs)
        self.cert_selection = cert_selection

    def __getattr__(self, name):
        return getattr(self.sock, name)

    def _pick_certificate_cb(self, connection):
        """SNI certificate callback.

        This method will set a new OpenSSL context object for this
        connection when an incoming connection provides an SNI name
        (in order to serve the appropriate certificate, if any).

        :param connection: The TLS connection object on which the SNI
            extension was received.
        :type connection: :class:`OpenSSL.Connection`

        """
        pair = self.cert_selection(connection)
        if pair is None:
            self.log_callback("SSL Socket: Certificate selection for server name {0} failed, dropping SSL".format(connection.get_servername()))
            return
        key, cert = pair
        new_context = SSL.Context(self.method)
        new_context.set_options(SSL.OP_NO_SSLv2)
        new_context.set_options(SSL.OP_NO_SSLv3)
        new_context.use_privatekey(key)
        new_context.use_certificate(cert)
        if self.alpn_selection is not None:
            new_context.set_alpn_select_callback(self.alpn_selection)
        connection.set_context(new_context)

    class FakeConnection(object):
        """Fake OpenSSL.SSL.Connection."""

        # pylint: disable=too-few-public-methods,missing-docstring

        def __init__(self, connection):
            self._wrapped = connection

        def __getattr__(self, name):
            return getattr(self._wrapped, name)

        def shutdown(self, *unused_args):
            # OpenSSL.SSL.Connection.shutdown doesn't accept any args
            return self._wrapped.shutdown()

    def accept(self):  # pylint: disable=missing-docstring
        sock, addr = self.sock.accept()
        context = SSL.Context(self.method)
        context.set_options(SSL.OP_NO_SSLv2)
        context.set_options(SSL.OP_NO_SSLv3)
        context.set_tlsext_servername_callback(self._pick_certificate_cb)
        if self.alpn_selection is not None:
            context.set_alpn_select_callback(self.alpn_selection)
        ssl_sock = self.FakeConnection(SSL.Connection(context, sock))
        ssl_sock.set_accept_state()
        self.log_callback("SSL Socket: Performing handshake with {0}".format(addr))
        try:
            ssl_sock.do_handshake()
        except SSL.Error as error:
            # _pick_certificate_cb might have returned without
            # creating SSL context (wrong server name)
            raise socket.error(error)

        return ssl_sock, addr


class BaseRequestHandlerWithLogging(socketserver.BaseRequestHandler):
    """BaseRequestHandler with logging."""

    log_callback = []

    def log_message(self, format, *args):
        """Log arbitrary message."""
        for callback in self.log_callback:
            callback("TLS Server request: {0} - - {1}".format(self.client_address[0], format % args))

    def handle(self):
        """Handle request."""
        self.log_message("Incoming request")
        super(BaseRequestHandlerWithLogging, self).handle()


class BadALPNProtos(Exception):
    """Error raised when cannot negotiate ALPN protocol."""
    pass


class TLSALPN01Server(socketserver.TCPServer):
    ACME_TLS_1_PROTOCOL = b"acme-tls/1"

    def __init__(self, server_address, certs, challenge_certs, log_callback):
        self.ipv6 = False
        self.address_family = socket.AF_INET
        self.certs = certs
        self.challenge_certs = challenge_certs
        self.allow_reuse_address = True
        self.log_callback = log_callback
        BaseRequestHandlerWithLogging.log_callback.append(log_callback)  # Ugly hack, but works...
        super(TLSALPN01Server, self).__init__(server_address, BaseRequestHandlerWithLogging)

    def _cert_selection(self, connection):
        # TODO: We would like to serve challenge cert only if asked for it via
        # ALPN. To do this, we need to retrieve the list of protos from client
        # hello, but this is currently impossible with openssl [0], and ALPN
        # negotiation is done after cert selection.
        # Therefore, currently we always return challenge cert, and terminate
        # handshake in alpn_selection() if ALPN protos are not what we expect.
        # [0] https://github.com/openssl/openssl/issues/4952
        server_name = connection.get_servername()
        self.log_callback("TLS ALPN Challenge server: Serving challenge cert for server name {0}".format(server_name))
        # return self.certs.get(server_name, None)
        if server_name.endswith(b'.'):
            server_name = server_name[:-1]
        return self.challenge_certs.get(server_name)

    def _alpn_selection(self, _connection, alpn_protos):
        """Callback to select alpn protocol."""
        if len(alpn_protos) == 1 and alpn_protos[0] == self.ACME_TLS_1_PROTOCOL:
            self.log_callback("TLS ALPN Challenge server: Agreed on {0} ALPN".format(self.ACME_TLS_1_PROTOCOL))
            return self.ACME_TLS_1_PROTOCOL
        # Raising an exception causes openssl to terminate handshake and
        # send fatal tls alert.
        self.log_callback("TLS ALPN Challenge server: Cannot agree on ALPN proto. Got: {0}".format(alpn_protos))
        raise BadALPNProtos("Got: {0}".format(alpn_protos))

    def _wrap_sock(self):
        self.socket = SSLSocket(self.socket, self.log_callback, cert_selection=self._cert_selection, alpn_selection=self._alpn_selection)

    def server_bind(self):
        self._wrap_sock()
        return super(TLSALPN01Server, self).server_bind()


class ALPNChallengeServer(object):
    def __init__(self, port, log_callback):
        self.certs = {}
        self.challenge_certs = {}
        self.server = None
        self.thread = None
        self.port = port
        self.log_callback = log_callback

    def add(self, domain, key, cert_normal, cert_challenge):
        if domain.endswith('.'):
            domain = domain[:-1]
        domain = domain.encode('utf-8')
        self.certs[domain] = (key, cert_normal)
        self.challenge_certs[domain] = (key, cert_challenge)

    def remove(self, domain):
        if domain.endswith('.'):
            domain = domain[:-1]
        domain = domain.encode('utf-8')
        self.certs.pop(domain)
        self.challenge_certs.pop(domain)

    def update(self):
        if self.server is None and self.certs:
            self.log_callback('Launching TLS ALPN challenge server...')
            self.server = TLSALPN01Server(("", self.port), certs=self.certs, challenge_certs=self.challenge_certs, log_callback=self.log_callback)
            self.thread = threading.Thread(target=self.server.serve_forever)
            self.thread.daemon = True
            self.thread.start()


def gen_ss_cert(key, domains, ips, extensions):
    cert = crypto.X509()
    cert.set_serial_number(int(binascii.hexlify(os.urandom(16)), 16))
    cert.set_version(2)
    extensions.append(crypto.X509Extension(b"basicConstraints", True, b"CA:TRUE, pathlen:0"))
    cert.set_issuer(cert.get_subject())
    sans = []
    sans.extend([b"DNS:" + d.encode() for d in domains])
    sans.extend([b"IP:" + d.encode() for d in ips])
    extensions.append(crypto.X509Extension(b"subjectAltName", critical=False, value=b", ".join(sans)))
    cert.add_extensions(extensions)
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(24 * 60 * 60)
    cert.set_pubkey(key)
    cert.sign(key, "sha256")
    return cert


__all__ = ['ALPNChallengeServer', 'gen_ss_cert']
