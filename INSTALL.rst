Dependencies
------------

- Python 2.6 or higher, including Python 3
- pySerial (for RS232 support) 2.5 or higher
- PyUSB (for USB support) 1.0 or higher

Installing dependencies on Ubuntu
---------------------------------

You should install the latest versions of pySerial and PyUSB via pip.
To get pip on Ubuntu, use apt to install::

 $ sudo apt-get install python3-pip

Or if you are holding out on 2.7::

 $ sudo apt-get install python-pip

If you installed pip for Python 3, replace 'pip' below with 'pip-3.2' (or 'pip-3.3')::

 $ pip install pyserial pyusb

It is recommended that you install the dependencies in a virtual environment
if you are developing with the pyATK libraries.

Running pyATK in-tree
---------------------

The command line version of pyATK. mx-flashtool, can be run in the source checkout without
setting the PYTHONPATH, as long as you are within the root of the checkout::

  ~/pyatk $ python bin/mx-flashtool --help



Installing pyATK library
------------------------

To install the pyATK library from source into your Python distribution
or virtual environment::

  ~/pyatk $ python setup.py install
  ...
  ~/pyatk $ python
  Python 2.7.3 (default, Aug  1 2012, 05:14:39)
  [GCC 4.6.3] on linux2
  Type "help", "copyright", "credits" or "license" for more information.
  >>> import pyatk
  >>>

