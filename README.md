# acme-test-container

[![Build Status](https://dev.azure.com/ansible/acme-test-container/_apis/build/status/CI?branchName=main)](https://dev.azure.com/ansible/acme-test-container/_build?definitionId=11)

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

## Release process

Merging a pull request (PR) builds an image and pushes it to [quay.io/ansible/acme-test-container](https://quay.io/repository/ansible/acme-test-container?tab=tags) with the `main` tag.
Note that pushing directly to `main` is forbidden, you always need to go through a PR.

Create a new GitHub Release with the desired version as the tag. This will trigger a pipeline which builds the image with the version number as the image tag, and pushes it to [quay.io/ansible/acme-test-container](https://quay.io/repository/ansible/acme-test-container?tab=tags).

## License and Copyright

Some of the code (collected in [acme_tlsalpn.py](acme_tlsalpn.py)) has been taken from
[Certbot's ACME library](https://github.com/certbot/certbot/tree/master/acme)
and is licensed under the Apache License 2.0, which can be found in [LICENSE-acme](LICENSE-acme).
This code is copyright 2015 Electronic Frontier Foundation and others.

The controller, Dockerfile and all other files are licensed under the GPL v3 (or later).
You can find the license in [LICENSE](LICENSE).
