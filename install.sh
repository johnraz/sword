#!/bin/sh
 if [ "$(id -u)" != "0" ]; then

    echo "This script must be run as root" 1>&2

    exit 1

fi



echo "Script starts";

if ! builtin type -p easy_install &>/dev/null; then

    echo "Installing setuptools"

    apt-get -y install python-setuptools

    echo "DONE"

fi



if ! builtin type -p curl &>/dev/null; then

    echo "Installing curl"

    apt-get -y install curl

    echo "DONE"

fi



if ! builtin type -p pip &>/dev/null; then

    echo "Installing pip"

    curl https://raw.github.com/pypa/pip/master/contrib/get-pip.py | python

    echo "DONE"

fi

if builtin type -p pip &>/dev/null; then

    echo "Installing sword requirements"

    pip install -r requirements.txt

    echo "DONE"

fi