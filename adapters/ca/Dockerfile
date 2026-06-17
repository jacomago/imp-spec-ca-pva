# CA DBR adapter image (Phase 0c-3).
#
# Follows the dependency-sourcing principle from ROADMAP.md: EPICS comes from
# conda-forge as pinned binaries, never built from source. The codec itself is
# pure ctypes (adapters/ca/) and needs no EPICS at all; pyepics/libca are
# installed here so the real-EPICS cross-check (tests/test_ca_epics.py) can run
# and so the adapter's provenance records concrete epics-base + pyepics versions.
#
# Build from the repo root (the build context is the repo, not adapters/ca):
#   docker build -f adapters/ca/Dockerfile -t ca-adapter .
# Run the adapter (JSON Lines corpus in -> JSON Lines artifacts out):
#   docker run --rm -i ca-adapter < adapters/ca/corpus/seed.jsonl
# Run the in-image verification (the libca cross-check + golden fixtures):
#   docker run --rm --entrypoint pytest ca-adapter -q

FROM condaforge/miniforge3:26.3.2-3

# Pinned conda-forge binaries. These exact versions surface in the adapter's
# provenance `extra` (read back at runtime from pyepics / libca).
ARG EPICS_BASE_VERSION=7.0.9.0
ARG PYEPICS_VERSION=3.5.10
RUN mamba install -y -n base -c conda-forge \
        "epics-base=${EPICS_BASE_VERSION}" \
        "pyepics=${PYEPICS_VERSION}" \
    && mamba clean -afy

# conda-forge epics-base ships its shared libs under an arch-specific dir that
# isn't on the default loader path, and pyepics' bundled stub libca doesn't
# cover aarch64. Symlink the host-arch EPICS libs into the conda lib dir and
# point pyepics straight at libca, so loading is arch-independent (x86_64 in CI,
# aarch64 on Apple silicon).
RUN set -eux; \
    archdir="$(dirname "$(find /opt/conda/epics/lib -path "*$(uname -m)*/libca.so" | head -1)")"; \
    ln -sf "$archdir"/*.so* /opt/conda/lib/
ENV PYEPICS_LIBCA=/opt/conda/lib/libca.so \
    LD_LIBRARY_PATH=/opt/conda/lib \
    CA_ADAPTER_EPICS_BASE=${EPICS_BASE_VERSION}

WORKDIR /app

# Just the bits the adapter and its tests read: the harness core, the CA adapter,
# the golden fixtures it is adjudicated against, the schemas it validates I/O
# against, and the test suite.
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY adapters/ ./adapters/
COPY schemas/ ./schemas/
COPY fixtures/ ./fixtures/
COPY docs/ ./docs/
COPY tests/ ./tests/

# pytest + jsonschema come from pip; pyepics is already supplied by conda above
# (it is deliberately not in the pip `[dev]` extra).
RUN pip install -e ".[dev]"

# The out-of-tree adapter package (`import ca`) lives under adapters/; pytest
# adds it via pyproject's `pythonpath`, but `python -m ca` needs it on the path
# too. The harness core is importable via the editable install above.
ENV PYTHONPATH=/app/adapters

# The image *is* the adapter (the Phase 1 producer contract): JSON Lines requests
# on stdin -> responses on stdout, via harness.io.run_adapter. Override the
# entrypoint to run the verification: docker run --entrypoint pytest <image> -q
ENTRYPOINT ["python", "-m", "ca"]
