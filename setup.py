from setuptools import setup, find_packages

setup(
    name="go2web",
    version="0.1",
    packages=find_packages(),
    install_requires=[],
    entry_points={
        "console_scripts": [
            "go2web=go2web.cli:main",
        ],
    },
)
