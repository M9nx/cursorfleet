# Optional runtime image for GitHub Container Registry (ghcr.io).
# Primary install path remains PyPI: pip install cursorfleet
FROM python:3.12-slim-bookworm

ARG CURSORFLEET_VERSION
RUN test -n "${CURSORFLEET_VERSION}" || (echo "CURSORFLEET_VERSION build-arg required" >&2 && exit 1)

RUN pip install --no-cache-dir "cursorfleet==${CURSORFLEET_VERSION}"

ENTRYPOINT ["cursorfleet"]
CMD ["--help"]
