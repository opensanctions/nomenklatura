from setuptools import setup, find_packages

setup(
    name='linkspotting',
    version='0.1',
    description="Make record linkages on the web.",
    long_description='',
    classifiers=[
        ],
    keywords='data mapping identity linkage record',
    author='Open Knowledge Foundation',
    author_email='info@okfn.org',
    url='http://okfn.org',
    license='AGPLv3',
    packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
    namespace_packages=[],
    include_package_data=False,
    zip_safe=False,
    install_requires=[
        'sqlalchemy==0.7.8',
        'Flask==0.9',
        'Flask-Script==0.3.3',
        'flask-sqlalchemy==0.16',
        'SQLAlchemy==0.7.8',
        'requests==0.13.2'
    ],
    tests_require=[],
    entry_points=\
    """ """,
)
