from setuptools import setup, find_packages

with open("README.md") as f:
    long_description = f.read()


setup(
    name="nomenklatura",
    version="0.1",
    description="Make record linkages on the web.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    classifiers=[],
    keywords="data mapping identity linkage record",
    author="Friedrich Lindenberg",
    author_email="friedrich@pudo.org",
    url="https://github.com/pudo/nomenklatura",
    license="MIT",
    packages=find_packages(exclude=["ez_setup", "examples", "tests"]),
    namespace_packages=[],
    include_package_data=False,
    zip_safe=False,
    install_requires=[],
    tests_require=[],
    entry_points={"console_scripts": ["nk = nomenklatura.manage:main"]},
)
