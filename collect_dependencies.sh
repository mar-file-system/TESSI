#!/bin/bash
set -e

# Capture system packages
dnf list installed | awk '{print $1}' > installed_packages.txt

# Capture Python 3.8 packages
pip3.8 freeze > requirements.txt

git add installed_packages.txt requirements.txt
git commit -m "Adding tassi requirements and dependencies"
git push

