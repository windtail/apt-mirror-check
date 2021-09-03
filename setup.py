# coding: utf-8


from setuptools import setup


setup(
    name="apt_mirror_check",
    version="1.0.2",
    description="Check corrupted files downloaded by apt-mirror",
    license="MIT",
    author="Luo Jiejun",
    author_email="6020100326ljj@163.com",
    install_requires=["click"],
    py_modules=["apt_mirror_check"],
    url="https://github.com/windtail/apt_mirror_check",
    entry_points={
        "console_scripts": [
            "apt-mirror-check = apt_mirror_check:cli"
        ]
    }
)
