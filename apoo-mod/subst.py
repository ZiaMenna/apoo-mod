#!/usr/bin/python
from sys import __stdin__, __stdout__, argv
import sys, string

if len(argv) != 3:
    print "Usage: subst.py str1 str2"
    print "  substitutes str1 with str2 in te stdin."
    sys.exit(1)

for line in __stdin__.readlines():
    line = string.replace(line,argv[1],argv[2])
    print line,
