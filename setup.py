from setuptools import setup, find_packages

setup(
    name="nomenklatura",
    version="0.1",
    description="Make record linkages on the web.",
    long_description="",
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
