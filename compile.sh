#!/bin/bash
nuitka start.py --recurse-all --recurse-not-to=gevent --remove-output
