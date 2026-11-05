# Shared image for the `mcp` and `app` services. Dependencies only: embeddings come from
# the Voyage API (VOYAGE_API_KEY at runtime). The repo's code is
# bind-mounted at /workspace, so `git checkout stage-N` needs no rebuild.
FROM python:3.12.16-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

ENV PYTHONPATH=/workspace

COPY docker/py/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

WORKDIR /workspace
ENTRYPOINT ["entrypoint.sh"]
CMD ["sleep", "infinity"]
