FROM python@sha256:94c362db08c5b38857943d31b10558ff1856e918605c474d205d72a534929d4e AS dependencies
COPY constraints.txt /constraints.txt
ENV PIP_CONSTRAINT=/constraints.txt
COPY matplotlib-0.0.1-cp310-cp310-linux_aarch64.whl /wheel/matplotlib-0.0.1-cp310-cp310-linux_aarch64.whl
RUN python -m pip wheel --wheel-dir /wheelhouse pip pytest '/wheel/matplotlib-0.0.1-cp310-cp310-linux_aarch64.whl'
FROM python@sha256:68d914ec641a0b69267ce65184d000a2bc3a9ee2590ab702b82250ab2385735a AS runtime_dependencies
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY constraints.txt /constraints.txt
ENV PIP_CONSTRAINT=/constraints.txt
COPY --from=dependencies /wheelhouse /wheelhouse
RUN rm /wheelhouse/matplotlib-0.0.1-cp310-cp310-linux_aarch64.whl
RUN python -m pip install --no-index --no-deps /wheelhouse/*.whl
FROM runtime_dependencies AS font_preparation
COPY tree /attest/tree
RUN --network=none ["python", "-c", "import os,sys; sys.dont_write_bytecode=True; os.environ['MPLCONFIGDIR']='/attest/mpl'; sys.path.insert(0,'/attest/tree/lib'); import matplotlib.font_manager"]
RUN --network=none chmod -R a+rX /attest/mpl
FROM runtime_dependencies
COPY --from=font_preparation /attest/mpl /attest/mpl
RUN python -m pip freeze > /runtime-freeze.txt
