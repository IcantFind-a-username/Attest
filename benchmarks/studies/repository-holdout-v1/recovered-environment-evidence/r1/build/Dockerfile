FROM --platform=linux/amd64 python@sha256:9e0b4f32487ca1863b45383420b8db77990debae748e2e875d2f86fa9510d4a5
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
RUN python -m pip install pip==20.1.1 setuptools==46.4.0 wheel==0.34.2
COPY requirements.txt /requirements.txt
RUN python -m pip install Cython==0.29.19
ENV NPY_NUM_BUILD_JOBS=2
COPY archives /archives
RUN python -m pip wheel --no-deps --no-build-isolation /archives/numpy-1.19.0rc2.tar.gz --wheel-dir /wheels && sha256sum /wheels/*
RUN python -m pip install --no-index --no-deps --find-links=/wheels numpy==1.19.0rc2
RUN python -m pip install --no-build-isolation --find-links=/archives -r /requirements.txt
COPY verify-pins.py /verify-pins.py
RUN python /verify-pins.py
RUN (python --version; gcc --version; dpkg-query -W; sha256sum /wheels/*) > /build-environment.txt && cat /build-environment.txt
RUN python -m pip check && python -m pip freeze > /environment.txt
