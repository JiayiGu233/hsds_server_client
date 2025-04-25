from setuptools import setup, find_packages

setup(
    name="hsds-client",
    version="0.1.0",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "hscli=hsds_client.cli:main",   # CLI（可选）
        ],
    },
)
