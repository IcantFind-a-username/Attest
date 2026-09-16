FROM python@sha256:94c362db08c5b38857943d31b10558ff1856e918605c474d205d72a534929d4e AS dependencies
COPY constraints.txt /constraints.txt
ENV PIP_CONSTRAINT=/constraints.txt
COPY native_fixture-0.1-cp310-cp310-linux_aarch64.whl /wheel/native_fixture-0.1-cp310-cp310-linux_aarch64.whl
RUN python -m pip wheel --wheel-dir /wheelhouse pip pytest '/wheel/native_fixture-0.1-cp310-cp310-linux_aarch64.whl'
FROM python@sha256:68d914ec641a0b69267ce65184d000a2bc3a9ee2590ab702b82250ab2385735a
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY constraints.txt /constraints.txt
ENV PIP_CONSTRAINT=/constraints.txt
COPY --from=dependencies /wheelhouse /wheelhouse
RUN python -m pip install --no-index --find-links /wheelhouse pip pytest '/wheelhouse/native_fixture-0.1-cp310-cp310-linux_aarch64.whl'
RUN python -m pip freeze > /runtime-freeze.txt
