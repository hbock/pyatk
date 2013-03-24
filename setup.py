from setuptools import setup

setup(
    name='pyatk',
    version='0.1.0',
    description='Python implementation of the Freescale bootloader protocol for i.MX processors.',
    author='Harry Bock',
    author_email='bock.harryw@gmail.com',

    packages=[
        'pyatk',
        'pyatk.channel',
        'pyatk.tests',
    ],
    test_suite='pyatk.tests',
    scripts=['bin/flashtool.py'],
    install_requires=[
        'pyserial >= 2.6',
        'pyusb >= 1.0.0a3',
    ],

    license='BSD',
    url='https://github.com/hbock/pyatk',
    long_description="""
``pyATK`` (Python ATK) is an attempt at replacing the Advanced Toolkit
(ATK) program distributed by Freescale Semiconductor for their i.MX
series processors.
""",
)
