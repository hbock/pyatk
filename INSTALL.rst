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

If you installed pip for Python 3, replace 'pip' below with 'pip-3.2'::

 $ pip install pyserial pyusb


Running pyATK in-tree
---------------------

The command line version of pyATK can be run in the source checkout without
setting the PYTHONPATH, as long as you are within the root of the checkout::

  ~/pyatk $ ./atk.py --help

Installing pyATK
----------------

Currently, pyATK provides no installation mechanism.  pip packages should
come soon!
