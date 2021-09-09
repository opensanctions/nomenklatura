from setuptools import setup, find_packages

with open("README.md") as f:
    long_description = f.read()


setup(
    name="nomenklatura",
    version="0.0.1",
    description="Make record linkages in followthemoney data.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    keywords="data mapping identity followthemoney linkage record",
    author="Friedrich Lindenberg",
    author_email="friedrich@pudo.org",
    url="https://github.com/pudo/nomenklatura",
    license="MIT",
    packages=find_packages(exclude=["ez_setup", "examples", "tests"]),
    namespace_packages=[],
    include_package_data=True,
    package_data={"nomeklatura": ["py.typed"]},
    zip_safe=False,
    install_requires=["followthemoney >= 2.6.2"],
    tests_require=[],
    entry_points={"console_scripts": ["nk = nomenklatura.cli:main"]},
    extras_require={
        "dev": [
            "wheel>=0.29.0",
            "twine",
            "mypy",
            "flake8>=2.6.0",
            "nose",
            "coverage>=4.1",
        ]
    },
)
