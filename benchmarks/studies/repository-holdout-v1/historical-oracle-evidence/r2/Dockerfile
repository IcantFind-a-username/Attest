FROM --platform=linux/amd64 python@sha256:baf4188f0b50c6383fedd55cdb79f511bfabee23068dcf26f209426f4bf540ab
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
RUN python -m pip install pip==20.1.1 setuptools==46.4.0 wheel==0.34.2
COPY requirements.txt /requirements.txt
RUN python -m pip install -r /requirements.txt
RUN python -m pip check && python -m pip freeze > /environment.txt
