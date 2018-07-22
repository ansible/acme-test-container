# acme-test-container

A container for integration testing ACME protocol modules.

Uses [Pebble](https://github.com/letsencrypt/Pebble).

## Usage

Building the image locally
```
docker image build -t local/ansible/acme-test-container:latest .
```

Building the image locally with a different version of Pebble checked out
```
docker image build --build-arg PEBBLE_CHECKOUT=<hash|branch|tag> -t local/ansible/acme-test-container:<hash|branch|tag> .
```

## License and Copyright

Some of the code (collected in [acme_tlsalpn.py](acme_tlsalpn.py)) has been taken from
[Certbot's ACME library](https://github.com/certbot/certbot/tree/master/acme)
and is licensed under the Apache License 2.0, which can be found in [LICENSE-acme](LICENSE-acme).
This code is copyright 2015 Electronic Frontier Foundation and others.

The controller, Dockerfile and all other files are licensed under the GPL v3 (or later).
You can find the license in [LICENSE](LICENSE).
