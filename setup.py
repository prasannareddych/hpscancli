from setuptools import setup, find_packages

# Retained for backwards compatibility with legacy pip versions
setup(
    name='hpscancli',
    version='1.1.0',
    packages=find_packages(),
    install_requires=[
        'requests>=2.28.0'
    ],
    entry_points={
        'console_scripts': [
            'hpscancli = hpscancli.cli:main'
        ]
    }
)
