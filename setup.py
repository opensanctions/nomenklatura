from setuptools import setup, find_packages

with open("README.md") as f:
    long_description = f.read()


setup(
    name="nomenklatura",
    version="3.5.2",
    description="Make record linkages in followthemoney data.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    keywords="data mapping identity followthemoney linkage record",
    author="Friedrich Lindenberg",
    author_email="friedrich@pudo.org",
    url="https://github.com/opensanctions/nomenklatura",
    license="MIT",
    packages=find_packages(exclude=["ez_setup", "examples", "tests"]),
    namespace_packages=[],
    include_package_data=True,
    package_data={"": ["nomenklatura/data/*", "nomenklatura/py.typed"]},
    zip_safe=False,
    install_requires=[
        "followthemoney >= 3.3.0, < 4.0.0",
        "shortuuid >= 1.0.11, < 2.0.0",
        "jellyfish >= 1.0.0, < 2.0.0",
        "rich >= 10.9.0, < 14.0.0",
        "textual >= 0.19.0, < 1.0.0",
        "scikit-learn == 1.3.1",
        "python-stdnum >= 1.19, < 2.0",
        "pydantic > 2.0.0, < 3.0.0",
        "click < 9.0.0",
        "plyvel < 2.0.0",
    ],
    tests_require=[],
    entry_points={
        "console_scripts": [
            "nk = nomenklatura.cli:cli",
            "nomenklatura = nomenklatura.cli:cli",
        ],
    },
    extras_require={
        "dev": [
            "wheel>=0.29.0",
            "twine",
            "mypy",
            "flake8>=2.6.0",
            "pytest",
            "pytest-cov",
            "coverage>=4.1",
            "types-setuptools",
            "types-requests",
            "requests-mock",
        ],
        "leveldb": ["plyvel"],
    },
)
