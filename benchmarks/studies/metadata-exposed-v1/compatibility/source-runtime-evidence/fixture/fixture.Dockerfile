FROM python@sha256:94c362db08c5b38857943d31b10558ff1856e918605c474d205d72a534929d4e
COPY tree /source
RUN python -m pip install setuptools==67.1.0 wheel==0.38.4
WORKDIR /source
RUN python setup.py bdist_wheel -d /wheels
