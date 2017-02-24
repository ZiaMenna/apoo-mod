#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
contants for Apoo

Copyright (C) 1998-2003 RogÃ©rio Reis & Nelma Moreira {rvr,nam}@ncc.up.pt

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.   

@author: Rogério Reis & Nelma Moreira {rvr,nam}@ncc.up.pt
"""

import exceptions
__version = "$Id: constants.py,v 1.27 2006-04-15 22:10:24 rvr Exp $"

False = 0
True = 1

class vpuError(Exception):
    pass

class EndOfProgram(vpuError):
    def __init__(self):
        self.message = 'End Of Program'
        self.colour = 'green'

class OutOfMemory(vpuError):
    def __init__(self,add):
        self.message = 'Out of Memory'
        self.add = add
        self.colour = 'red'
        
class OutOfProgram(vpuError):
    def __init__(self):
        self.message = 'Out of Program'
        self.colour = 'red'
        
class LabelError(vpuError):
    def __init__(self,line = 0):
        self.message = 'Label Error'
        self.line = line
        self.colour = 'red'
        
class LabelNameError(vpuError):
    def __init__(self,line = 0):
        self.message = 'Label Name Error'
        self.line = line
        self.colour = 'red'
        
class TooManySteps(vpuError):
    def __init__(self, num):
        self.message = 'Probably an infinite loop'
        self.num = num
        self.colour = 'red'
        
class vpuLoadError(vpuError):
    def __init__(self, line):
        self.line = line
        
class BadArgs(vpuLoadError):
    def __init__(self,line):
        self.message = 'Wrong number of arguments'
        vpuLoadError.__init__(self,line)
        
class WrongArg(vpuLoadError):
    def __init__(self,line):
        self.message = 'Wrong argument'
        vpuLoadError.__init__(self,line)
        
class NotInt(vpuLoadError):
    def __init__(self,line):
        self.message = 'Integer expected'
        vpuLoadError.__init__(self,line)

class IllInst(vpuLoadError):
    def __init__(self,line):
        self.message = 'Illegal Instruction'
        vpuLoadError.__init__(self,line)
        
class IllOperand(vpuLoadError):
    def __init__(self,line):
        self.message = 'Illegal Operand'
        vpuLoadError.__init__(self,line)

class IllReg(vpuLoadError):
    def __init__(self,line):
        self.message = 'Illegal Register'
        vpuLoadError.__init__(self,line)

class FileError(vpuError):
    def __init__(self,line=0):
        self.message = 'File Error'
        
class MemoryUnderflow(vpuError):
    def __init__(self,add):
        self.message = 'Memory Underflow'
        self.add = add
        self.colour = 'red'

# zero arg, nonreg, reg, reg reg, nonreg reg, reg nonreg, specials
inst = (['rtn','halt','nop'], # zero arg
        ['jsr','jump'], # nonreg
        ['inc','dec','zero','not','jumpi','push','pop'], #reg
        ['storei','loadi','storer','add','sub','mul','div','mod',
         'and','or','xor'], # reg reg
        ['load','loadn','loado'], # nonreg reg
        ['store','jzero','jnzero','jpos','jneg','storeo'], # reg nonreg
        ['mem','const','string','equ']) #specials




