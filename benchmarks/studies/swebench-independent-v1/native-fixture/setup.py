from setuptools import Extension, setup

setup(
    name="native-fixture", version="0.1", packages=["native_fixture"],
    ext_modules=[Extension("native_fixture._native", ["native_fixture/native.c"])],
)
