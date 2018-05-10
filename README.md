Overview
========
This project implements the various functionality of [sg_utils](http://sg.danny.cz/sg/sg3_utils.html).

Usage
-----
After installing, a new shell command "asi-utils" will be available, exposing various options, for example, INQUIRY commands:

    # instead of running sg_inq /dev/sda --page=0x00
    asi-utils inq /dev/sda --page=0x00

To see all the options and usage, run:

    asi-utils --help

Checking out the code
=====================
To run this code from the repository for development purposes, run the following:

    easy_install -U infi.projector
    projector devenv build

