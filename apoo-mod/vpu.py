#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Apoo Virtual Processor

Copyright (C) 1998-2006 Rogério Reis & Nelma Moreira {rvr,nam}@ncc.up.pt

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
from constants import *
import string, sys, time, copy


__version = "3.0p2"
Changed = (None,None)


class Vpu:
    def __init__(self, n=8, MpMem={}, Inter=None, RAMSize=1000):
        """This is where all the pseudo-code is specified. Any new
        intruction added shoud be added to the constants.py module
        too, where the lexical information resides.  @arg n: is the
        number of registers to support."""
        self.reg = []
        self.nreg = n
        for i in range(n): self.reg.append(0)
        self.RAM = []
        self.Prog = []
        self.labelp = {}
        self.labelm = {}
        self.labelms = {}
        self.constants = {}
        self.PC = 0
        self.SPn = n-1
        self.FPn = n-2
        self.BreakP = []
        self.StaticMem = 0
        self.lines = []
        self.time0, self.time = 0,0
        self.Inter=Inter
        self.RAMSize = RAMSize
        self.MpMem = copy.deepcopy(MpMem)
        self.code = {'add':("Reg[A2] = Reg[A2] + Reg[A1]",
                            "incPC()"),
                     'and':("Reg[A2] = Reg[A1] & Reg[A2]",
                            "incPC()"),
                     'dec':("Reg[A1] = Reg[A1] - 1",
                            "incPC()"),
                     'div':("Reg[A2] = Reg[A1] / Reg[A2]",
                            "incPC()"),
                     'halt':("raise EndOfProgram"),
                     'inc':("Reg[A1] = Reg[A1] + 1",
                            "incPC()"),
                     'jneg':("if Reg[A1] < 0:",
                             " if type(A2) == type(''):",
                             "  add = self.ParseLabelP(A2)",
                             " else: add = A2",
                             " self.PC = add",
                             "else: self.PC = self.PC + 1"),
                     'jpos':("if Reg[A1] > 0:",
                             " if type(A2) == type(''):",
                             "  add = self.ParseLabelP(A2)",
                             " else: add = A2",
                             " self.PC = add",
                             "else: self.PC = self.PC + 1"),
                     'jsr':("if type(A1) == type(''):",
                            " add = self.ParseLabelP(A1)",
                            "else: add = A1",
                            "self.push(self.PC + 1)",
                            "self.PC = add"),
                     'jump':("if type(A1) == type(''):",
                             " try: add = self.labelp[A1]",
                             " except KeyError: raise LabelError",
                             "else: add = A1",
                             "self.PC = add"),
                     'jumpi':("self.PC = Reg[A1]"),
                     'jnzero':("if Reg[A1] != 0:",
                              " if type(A2) == type(''):",
                              "  add = self.ParseLabelP(A2)",
                              " else: add = i[2]",
                              " self.PC = add",
                              "else: self.PC = self.PC + 1"),
                     'jzero':("if Reg[A1] == 0:",
                              " if type(A2) == type(''):",
                              "  add = self.ParseLabelP(A2)",
                              " else: add = i[2]",
                              " self.PC = add",
                              "else: self.PC = self.PC + 1"),
                     'load':("if type(A1) == type(''):",
                             " try: add = self.labelm[A1]",
                             " except KeyError: raise LabelError",
                             "else: add = A1",
                             "try: foo = self.MLoad(add)",
                             "except IndexError: raise OutOfMemory(add)",
                             "Reg[A2] = foo",
                             "incPC()"),
                     'loadi':("add = Reg[A1]",
                              "try: foo = self.MLoad(add)",
                              "except IndexError: raise OutOfMemory(add)",
                              "Reg[A2] = foo",
                              "incPC()"),
                     'loadn':("if type(A1) == type(''):",
                              " v = self.ParseLabel(A1)",
                              "else: v = A1",
                              "Reg[A2] = v",
                              "incPC()"),
                     'loado':("add = Reg[self.FPn]+A1",
                              "try: foo = self.MLoad(add)",
                              "except IndexError: raise OutOfMemory(add)",
                              "Reg[A2] = foo",
                              "incPC()"),
                     'mod':("Reg[A2] = Reg[A1] % Reg[A2]",
                            "incPC()"),
                     'mul':("Reg[A2] = Reg[A1] * Reg[A2]",
                            "incPC()"),
                     'or':("Reg[A2] = Reg[A1] | Reg[A2]",
                           "incPC)"),
                     'pop':("Reg[A1] = self.pop()",
                            "incPC()"),
                     'push':("self.push(Reg[A1])",
                             "incPC()"),
                     'rtn':("self.PC = self.pop()"),
                     'store':("if type(A2) == type (''):",
                              " try: add = self.labelm[A2]",
                              " except KeyError: raise LabelError",
                              "else: add = A2",
                              "foo = Reg[A1]",
                              "try: self.MStore(add,foo)",
                              "except IndexError: raise OutOfMemory(add)",
                              "incPC()"),
                     'storei':("try: self.MStore(Reg[A2],Reg[A1])",
                               "except IndexError:",
                               " raise OutOfMemory(Reg[A2])",
                               "incPC()"),
                     'storen':("if type(A1) == type(''):",
                               " r = self.ParseLabel(A1)",
                               "else: r = A1",
                               "Reg[A2]=r",
                               "incPC()"),
                     'storeo':("add = Reg[self.FPn]+A2",
                               "try:self.MStore(add,Reg[A1])",
                               "except IndexError:",
                               " raise OutOfMemory(add)",
                               "incPC()"),
                     'storer':("Reg[A2] = Reg[A1]",
                               "incPC()"),
                     'sub':("Reg[A2] = Reg[A1] - Reg[A2]",
                            "incPC()"),
                     'xor':("Reg[A2] = Reg[A1] ^ Reg[A2]",
                            "incPC()"),
                     'nop':("incPC()"),
                     'zero':("Reg[A1] = 0",
                             "incPC()")}
        for k in self.code.keys():
            self.code[k] = expandCode(self.code[k])

    def clean(self):
        """Ensures all the memory areas are clean."""
        for i in range(self.nreg): self.reg[i]=0
        self.RAM = []
        self.Prog = []
        self.labelp = {}
        self.labelm = {}
        self.labelms = {}
        self.PC = 0
        self.BreakP = []
        self.lines = []
        self.time0, self.time = 0,0

    def __str__(self):
        """Only used for debugging purposes."""
        return str((self.PC,self.reg,self.reg[self.SPn]))

    def __repr__(self):
        """Only used for debugging purposes."""
        return 'Vpu( %s )'% self.__str__()

    def MStore(self,add,val):
        """Store in memory shell that deals with mapped memory """
        global Changed
        if add in self.MpMem.keys():
            exec self.MpMem[add][1]
        elif self.RAMSize <= add or add < 0:
            raise OutOfMemory(add)
        else:
            self.RAM[add] = val
            Changed = (add,val)

        
    def MLoad(self,add):
        """Load from RAM shell that deals with mapped memory """
        if add in self.MpMem.keys():
            val = 0
            exec self.MpMem[add][0]
            return val
        elif self.RAMSize <= add or add < 0:
            raise OutOfMemory(add)
        else:
            return self.RAM[add]
        
    def run(self, MaxSteps=1000):
        """Starts the execution of the current program.

        @arg MaxSteps: the maximum allowed number of steps to execute
        for infinite loop detection."""
        i = 0
        while True:
            self.step()
            if i > MaxSteps: raise TooManySteps(i)
            else: i = i + 1

    def setbreak(self,linum):
        """Create a breakpoint"""
        if not linum in self.BreakP: 
            self.BreakP.append(linum)

    def clearbreak(self,linum):
        """Clear a breakpoint"""
        if linum in self.BreakP: 
            del(self.BreakP[self.BreakP.index(linum)])

    def cont(self,num):
        i = 0
        while True:
            self.step()
            if i > num: raise TooManySteps(num)
            i = i + 1
            if self.PC in self.BreakP:
                return 

    def step(self):
        """basic execution of a step of the program"""
        global Changed
        Changed=(None,None)
        self.TimerOn()
        try:
            i = self.Prog[self.PC]
        except IndexError:
            self.TimerOff()
            raise OutOfProgram
        if type(i) == type(''): # no args
            exec self.code[i]
        else:
            exec self.code[i[0]]
        self.TimerOff()
        return Changed
    
    def incPC(self):
        self.PC = self.PC + 1
        
    def load(self,program):
        self.clean()
        for (n,i) in program:
            if len(i) < 2:
                if i[0] == []: raise LabelError(n)
                else: i.append('nop')
            if i[1] == 'equ':
                if len(i) != 3:
                    raise BadArgs(n)
                if i[0] == []:
                    raise BadArgs(n)
                else:
                    validateLabelName(i[0],n)
                    if isNumber(i[2]):
                        self.constants[i[0]]= int(i[2])
                    else:
                        raise BadArgs(n)
                continue
            if i[1] == 'const':
                if len(i) != 3:
                    raise BadArgs(n)
                if i[0] != []:
                    validateLabelName(i[0],n)
                    self.labelm[i[0]] = len(self.RAM)
                    self.labelms[i[0]] = 1
                    lastLabel = i[0]
                else:
                    self.labelms[lastLabel] = self.labelms[lastLabel] + 1
                r = charORint(i[2],n)
                self.RAM.append(r)
                continue
            if i[1] == "string":
                if len(i) != 3:
                    raise BadArgs(n)
                strarg = validateString(i[2],n)
                if i[0] != []:
                    validateLabelName(i[0],n)
                    self.labelm[i[0]] = len(self.RAM)
                    self.labelms[i[0]] = len(strarg)+1
                for j in strarg:
                    self.RAM.append(ord(j))
                self.RAM.append(0)
                continue
            if i[1] == 'mem':
                if len(i) != 3:
                    raise BadArgs(n)
                try: r = int(i[2])
                except ValueError:
                    raise NotInt(n)
                if i[0] != []:
                    validateLabelName(i[0],n)
                    self.labelm[i[0]] = len(self.RAM)
                    self.labelms[i[0]] = r  # this is only for tutor use 
                for foo in range(r):
                    self.RAM.append(0)
                continue
            if i[0] != []:
                validateLabelName(i[0],n)
                self.labelp[i[0]] = len(self.Prog)
            self.lines.append(n)
            if i[1] in inst[0]: # no args
                if len(i) != 2: raise BadArgs(n)
                else: self.Prog.append((i[1],))
            elif i[1] in inst[1]: # nonreg
                if len(i) != 3: raise BadArgs(n)
                else: self.Prog.append((i[1],self.ParseNum(i[2])))
            elif i[1] in inst[2]: # reg
                if len(i) != 3: raise BadArgs(n)
                r1 = ParseReg(i[2],self.nreg,n)
                self.Prog.append((i[1],r1))
            elif i[1] in inst[3]: # reg reg
                if len(i) != 4: raise BadArgs(n)
                r1 = ParseReg(i[2],self.nreg,n)
                r2 = ParseReg(i[3],self.nreg,n)
                self.Prog.append((i[1],r1,r2))
            elif i[1] in inst[4]: # nonreg reg
                if len(i) != 4: raise BadArgs(n)
                r1 = ParseReg(i[3],self.nreg,n)
                self.Prog.append((i[1],self.ParseNum(i[2]),r1))
            elif i[1] in inst[5]: # reg nonreg
                if len(i) != 4: raise BadArgs(n)
                r1 = ParseReg(i[2],self.nreg,n)
                self.Prog.append((i[1],r1,self.ParseNum(i[3])))
            else:
                raise IllInst(n)
        self.StaticMem = len(self.RAM)-1
        self.RAM += [ 0 for i in xrange(self.RAMSize)]
        self.reg[self.SPn] = self.StaticMem
        self.reg[self.FPn] = self.reg[self.SPn] + 1
        
    def push(self,val):
        self.reg[self.SPn] += 1
        self.MStore(self.reg[self.SPn],val)
        
    def pop(self):
        if self.reg[self.SPn] <= self.StaticMem:
            raise MemoryUnderflow(self.reg[self.SPn])
        foo = self.MLoad(self.reg[self.SPn])
        self.reg[self.SPn] -= 1
        return foo
        
    def ParseNum(self,st):
        if st in self.constants.keys():
            return self.constants[st]
        elif st[0] in string.digits or st[0] == '-':
            return int(st)
        else:
            return st
        
    def ParseLabel(self,st):
        try: r = self.labelm[st]
        except KeyError:
            raise LabelError
        return r

    def ParseLabelP(self,st):
        try: r = self.labelp[st]
        except KeyError:
            raise LabelError
        return r

    def destructLabel(self,label):
        if label in self.labelm.keys():
            del(self.labelm[label])
        if label in self.labelms.keys():
            del(self.labelms[label])

    def reserveMemory1(self,label,size):
        self.destructLabel(label)
        self.labelm[label] = len(self.RAM)
        for i in range(size):
            self.RAM.append(0)
        self.labelms[label] = size

    def relocateLabel(self,label,dif):
        for n in self.labelm.keys():
            if self.labelm[n] > self.labelm[label] :
                self.labelm[n] = self.labelm[n] + dif
        if dif > 0:
            for i in range(dif):
                self.RAM.insert(self.labelm[label],0)
        if dif < 0:
            self.RAM[(self.labelm[label]+ self.labelms[label] +dif):(self.labelm[label]+ self.labelms[label])]=[]

    def reserveMemory(self,label,size):
        if label in self.labelm.keys():
            if self.labelms[label] != size:
                dif = size - self.labelms[label]
                self.relocateLabel(label,dif)
            else:
                for i in range(size):
                    self.RAM[self.labelm[label]+i] = 0
        else:
            self.labelm[label] = len(self.RAM)
            for i in range(size):
                self.RAM.append(0)
        self.labelms[label] = size
            
    def TimerInit(self):
        self.time = 0

    def TimerOn(self):
        self.time0 = time.clock()

    def TimerOff(self):
        self.time = self.time + (time.clock() - self.time0)

def ReadProgram(filename):
    try:
        input = open(filename, 'r')
    except IOError:
        CantRead(filename)
    program = []
    linum = 0
    while 1:
        line = input.readline()
        linep = []
        linum = linum + 1
        if not line: break
        if len(line) == 1: continue
        line = string.split(line)
        if line:
            if line[0][len(line[0])-1] == ':' and line[0][0] != '#':
                linep.append(line[0][:len(line[0])-1])
            elif line[0][0] == '#':
                continue
            else:
                linep.append([])
                linep.append(line[0])
            for i in range(1,len(line)):
                if line[i][0] == '#': continue
                else: linep.append(line[i])
            program.append((linum,linep))
    return program

def CantRead(file):
    sys.stderr.write("Error: Cannot read file %s\n"%file)
    sys.exit(1)

def ParseReg(st,nreg,line):
    if st[0] != 'r' and st[0] != 'R':
        raise IllOperand(line)
    elif st == "RS" or st == "rs":
        st = "R%d"%(nreg-1)
    elif st == "RF" or st == "rf":
        st = "R%d"%(nreg-2)
    try: i = int(st[1:len(st)])
    except ValueError:
        raise IllOperand(line)
    if not i in range(nreg):
        raise IllReg(line)
    return i

def expandCode(list):
    if type(list) == type(''):
        return expandCode1(list)
    else:
        s = expandCode1(list[0])
        for i in list[1:]:
            s = s + "\n" + expandCode1(i)
        return s
    
def expandCode1(s):
    subst = (('A1','i[1]'),('A2','i[2]'),('A3','i[3]'),
             ('Reg','self.reg'),
             ('incPC()','self.incPC()'),
             ('RAM','self.RAM'))
    for i in subst:
        s = string.replace(s,i[0],i[1])
    return s

def isNumber(str):
    """Verifies if a string is a number representation"""
    for i in str:
        if i not in string.digits: return 0
    return 1

def validateLabelName(str,linenum):
    """Verifies if a candidate label name is not of the form R{num}.
    If the first character is a letter and only contains legal chars."""
    if str[0] not in string.letters:
        raise LabelNameError(linenum)
    if str[0] in ["R","r"] and isNumber(str[1:]):
        raise LabelNameError(linenum)
    for i in str[1:]:
        if i not in string.letters + string.digits:
            raise LabelNameError(linenum)

def validateString(i,n):
    arg = ""
    if i[0] != '"' or i[-1] != '"':
        raise WrongArg(n)
    flag = False
    for c in i[1:-1]:
        if not flag:
            if c == "\\":
                flag= True
            else:
                arg += c
        else:
            flag = False
            if c=="t":
                arg += "\t"
            if c=="s":
                arg += " "
            if c == "n":
                arg += "\n"
            if c == "\\":
                arg += "\\"
    return arg

def charORint(i,n):
    if i[0] != "'":
        try: r = int(i)
        except ValueError:
            raise WrongArg(n)
    elif i[-1] != "'": raise WrongArg(n)
    elif i[1] != "\\" and len(i) != 3: raise WrongArg(n)
    elif i[1] != "\\": r = ord(i[1])
    else:
        if len(i) != 4: raise WrongArg(n)
        elif i[2] == "n": r = ord("\n")
        elif i[2] == "s": r = ord(" ")
        elif i[2] == "t": r = ord("\t")
        elif i[2] == "\\": r = ord("\\")
        else: raise WrongArg(n)
    return r

def isRegName(str):
    """Verifies if this is a register name."""
    if str[0] not in ['r','R']:
        return 0
    elif not isNumber(str[1:]):
        return 0
    return 1

