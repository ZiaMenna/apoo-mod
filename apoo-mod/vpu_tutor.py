# -*- coding: UTF-8 -*-
"""
The core of an exercise tester in the spirit of the Ganesh project

Copyright (C) 1998-2003 Rogério Reis & Nelma Moreira {rvr,nam}@ncc.up.pt

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
from vpu import Vpu, ReadProgram, CantRead, isNumber, isRegName
import constants, vpu
# constants need to be imported twice because of -v option...
import sys, stat, posix, string

__version =  "$Id: vpu_tutor.py,v 1.29 2006-11-13 11:11:59 rvr Exp $"

class Vpu_Tutor(Vpu):
    def doIt(self):
        try:
            input = open(self.tutorFile,'r')
        except IOError:
            CantRead(self.tutorFile)
        self.ggrade = 0
        last, loaded, run = 'ready',0,0
        tutor = []
        # remove commands and create a tutor command list
        while 1:
            line = input.readline()
            if not line: break
            if len(line) == 1: continue
            line = string.split(line)
            if line:
                if line[0][0] == '#':
                    continue
                flag = 1
                for i in range(len(line)):
                    if line[i][0] != '#' and flag:
                        continue
                    else:
                        flag = 0
                        del(line[i])
            tutor.append(line)
        # now lets parse and execute the tutor file
        for line in tutor:
            if not line:
                continue
            if line[0] == 'load':
                if last != 'ready':
                    sys.stderr.write("error: load out of order\n")
                    sys.exit(1)
                last = 'load'
                run = 0
            elif line[0] == 'initial':
                if last != 'ready' or not loaded:
                    sys.stderr.write("error: initial out of order\n")
                    sys.exit(1)
                last = line[0]
                run = 0
                labelReq1 = {}
                labelReq2 = {}
                for arg in line[1:]:
                    if ':' in arg:
                        a = string.split(arg,':')
                        labelReq1[a[0]] = ParseValuesM(a[1])
                    elif ';' in arg:
                        a = string.split(arg,';')
                        labelReq2[a[0]] = int(a[1])
                    else:
                        sys.stderr.write("error: bad arguments for initial\n")
                        sys.exit(1)
            elif line[0] == 'init':
                if last == 'load':
                    sys.stdout.write("error: Not testing the initial set of values\n")
                    sys.exit(1)
                elif not loaded:
                    sys.stdout.write("error: program not loaded\n")
                    sys.exit(1)
                else:
                    self.load(program)
                    for arg in line[1:]:
                        foo = string.split(arg,':')
                        if isRegName(foo[0]):
                            bar = int(foo[0][1:])
                            self.reg[bar] = int(foo[1])
                        else:
                            self.VerifyLabelM(foo[0])
                            Values = ParseValuesM(foo[1])
                            # lets verify if the values fit
                            # in the originally allocated space
                            if len(Values) > self.labelms[foo[0]]:
                                self.reserveMemory(foo[0],len(Values))
                            add = self.labelm[foo[0]]
                            for i in Values:
                                self.RAM[add] = i
                                add = add + 1
                last = line[0]
                run = 0
            elif line[0] == 'exec':
                if not loaded:
                    sys.stdout.write("error: program not loaded\n")
                    sys.exit(1)
                else:
                    if len(line) == 1:
                        target = ""
                    else:
                        target = line[1]
                    run = 1
                    last = line[0]
            elif line[0] == 'final' or line[0] == '+final':
                last = line[0]
                if not run:
                    sys.stdout.write("error: need to run the program before testing the results\n")
                    sys.exit(1)
                RegVal = {}
                LabelReq1 = {}
                for arg in line[1:]:
                    foo = string.split(arg,':')
                    if isRegName(foo[0]):
                        RegVal[int(foo[0][1:])] = int(foo[1])
                    else:
                        LabelReq1[foo[0]] = ParseValuesM(foo[1])
            elif line[0] == 'end':
                if self.NoErrorsp():
                    sys.stdout.write("%d OK\n"%self.ggrade)
                else:
                    sys.stdout.write("%d %s"%(self.ggrade,self.ErrMessage))
                sys.exit(0)
            elif line[0] == 'value':
                grade = int(line[1])
                if not last in ['load','initial','exec','final','+final']:
                    sys.stderr.write("error: value out of order\n")
                    sys.exit(1)
                elif last == 'load':
                    program = ReadProgram(self.programFile)
                    try:
                        self.load(program)
                    except vpuError, obj:
                        self.respond(obj.message,obj.line)
                    loaded = 1
                    self.ggrade = self.ggrade + grade
                    last = 'ready'
                elif last == 'initial':
                    for l in labelReq1.keys():
                        self.VerifyLabel1(l,labelReq1[l])
                    for l in labelReq2.keys():
                        self.VerifyLabel2(l,labelReq2[l])
                    self.ggrade = self.ggrade + grade
                elif last == 'exec':
                    if target == "":
                        try:
                            self.run()
                        except EndOfProgram:
                            self.ggrade = self.ggrade + grade
                        except ArithmeticError:
                            self.respond(sys.exc_type)
                        except vpuError, obj:
                            self.respond(obj.message)
                        except: # this should NEVER happen!
                            print sys.exc_type, sys.exc_value 
                elif last == 'final':
                    for r in RegVal.keys():
                        self.VerifyReg(r,RegVal[r])
                    for r in LabelReq1.keys():
                        self.VerifyLabel1(r,LabelReq1[r])
                    self.ggrade = self.ggrade + grade
                elif last == '+final':
                    nErrors = 0
                    for r in RegVal.keys():
                        nErrors = nErrors + self.VerifyReg(r,RegVal[r],True)
                    for r in LabelReq1.keys():
                        nErrors = nErrors + self.VerifyLabel1(r,LabelReq1[r],True)
                    if not nErrors:
                        self.ggrade = self.ggrade + grade

    def VerifyReg(self, r, value, NotVital=False):
        if self.reg[r] != value:
            if NotVital:
                self.SetErrMsg("Register R%d does not have the right value\n"%r)
                return 1
            else:
                sys.stdout.write("%d Register R%d does not have the right value\n"%(self.ggrade,r))
                sys.exit(0)
        else:
            return 0
        
    def VerifyLabelM(self,label):
        if not label in self.labelm.keys():
            sys.stdout.write("%d Label %s not created\n"%(self.ggrade,label))
            sys.exit(0)
                    
    def VerifyLabel1(self, label, values, NotVital=False):
        self.VerifyLabelM(label)
        add = self.labelm[label]
        for v in values:
            try: Wrong = self.RAM[add] != v
            except IndexError:
                Wrong = True
            if Wrong:
                if NotVital:
                    self.SetErrMsg("Label %s does not have the right value\n"%label)
                    return 1
                else:
                    sys.stdout.write("%d Label %s does not have the right value\n"%(self.ggrade,label))
                    sys.exit(0)
            add = add + 1
        return 0
    
    def VerifyLabel2(self, label, size):
        self.VerifyLabelM(label)
        if self.labelms[label] != size:
            sys.stdout.write("%d Label %s does not have the right size assigned\n"%(self.ggrade,label))
            sys.exit(0)

    def NoErrorsp(self):
        try:
            foo = self.ErrMessage
        except AttributeError:
            return True
        return False
    
    def SetErrMsg(self,msg):
        try:
            foo = self.ErrMessage
        except AttributeError:
            self.ErrMessage = msg

    def respond(self,message,line=0):
        if line != 0:
            sys.stdout.write("%d %s in line %d\n"%(self.ggrade,message,line))
            sys.exit(0)
        else:
            sys.stdout.write("%d %s\n"%(self.ggrade,message))
            sys.exit(0)
            
def ParseValuesM(str):
    l1 = string.split(str,',')
    list = []
    for i in l1:
        list.append(int(i))
    return list

def readable(path):
    try:
        mode = posix.stat(path)[stat.ST_MODE]
    except OSError:               # File doesn't exist
        sys.stderr.write("%s not found\n"%path)
        sys.exit(1)
    if not stat.S_ISREG(mode):    # or it's not readable
        sys.stderr.write("%s not readable\n"%path)
        sys.exit(1)
    
# just to use inside pdb
def test(a,b):
    vPu = Vpu_Tutor()
    vPu.tutorFile = a
    vPu.programFile = b
    vPu.doIt()

if __name__ == '__main__':
    if (len(sys.argv) == 2 and sys.argv[1] == "-v"):
            sys.stderr.write("%s\n"%__version)
            sys.stderr.write("%s\n"%vpu.__version)
            sys.stderr.write("%s\n"%constants.__version)
            sys.exit(0)
    elif (len(sys.argv) != 3):
        sys.stderr.write("Usage: apoo-tutor tutor-file apoo-program\n")
        sys.exit(1)
    for i in [sys.argv[1],sys.argv[2]]:
        readable(i)
    vpu = Vpu_Tutor()
    vpu.tutorFile = sys.argv[1]
    vpu.programFile = sys.argv[2]
    vpu.doIt()

