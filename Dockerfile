FROM golang:1.23-bookworm AS builder
# Install pebble
ENV CGO_ENABLED=0
ARG PEBBLE_REMOTE=
ARG PEBBLE_CHECKOUT="ddbc6bef1a71bf09e6ca5a7ed4d20ae3882c2bb7"
WORKDIR /pebble-src
RUN git clone https://github.com/letsencrypt/pebble.git /pebble-src && \
    if [ "${PEBBLE_REMOTE}" != "" ]; then \
      git remote add other ${PEBBLE_REMOTE} && \
      git fetch other && \
      git checkout -b other-${PEBBLE_CHECKOUT} --track other/${PEBBLE_CHECKOUT}; \
    else \
      git checkout ${PEBBLE_CHECKOUT}; \
    fi && \
    go build -o /go/bin/pebble ./cmd/pebble

FROM python:3.13-slim-bookworm
# Install software
ADD requirements.txt /root/
RUN pip3 install -r /root/requirements.txt
# Install pebble
COPY --from=builder /go/bin/pebble /go/bin/pebble
COPY --from=builder /pebble-src/test /pebble-src/test
# Setup controller.py and run.sh
ADD run.sh controller.py dns_server.py acme_tlsalpn.py ocsp.py create-pebble-config.py LICENSE LICENSE-acme README.md /root/
EXPOSE 5000 14000
CMD [ "/bin/sh", "-c", "/root/run.sh" ]
