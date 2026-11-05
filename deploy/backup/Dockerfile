FROM postgres:18.6-trixie@sha256:bd5dfa494a5a259704365813dbfa5fa6b3e69be7348d43b547f540c730478583
RUN apt-get update \
    && apt-get install -y --no-install-recommends age \
    && rm -rf /var/lib/apt/lists/*
COPY backup.sh /usr/local/bin/backup.sh
ENTRYPOINT ["/usr/local/bin/backup.sh"]
