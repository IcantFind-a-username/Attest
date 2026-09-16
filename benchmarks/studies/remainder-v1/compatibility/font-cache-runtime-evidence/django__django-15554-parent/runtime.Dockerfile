FROM python@sha256:94c362db08c5b38857943d31b10558ff1856e918605c474d205d72a534929d4e AS dependencies
COPY constraints.txt /constraints.txt
ENV PIP_CONSTRAINT=/constraints.txt
COPY Django-4.0-py3-none-any.whl /wheel/Django-4.0-py3-none-any.whl
RUN python -m pip wheel --wheel-dir /wheelhouse pip pytest '/wheel/Django-4.0-py3-none-any.whl'
FROM python@sha256:68d914ec641a0b69267ce65184d000a2bc3a9ee2590ab702b82250ab2385735a AS runtime_dependencies
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY constraints.txt /constraints.txt
ENV PIP_CONSTRAINT=/constraints.txt
COPY --from=dependencies /wheelhouse /wheelhouse
RUN rm /wheelhouse/Django-4.0-py3-none-any.whl
RUN python -m pip install --no-index --no-deps /wheelhouse/*.whl
RUN python -m pip freeze > /runtime-freeze.txt
