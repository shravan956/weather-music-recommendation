@echo off
title MoodWave - Auto Start
cd /d "C:\Users\User\Documents\music project"
start "" /min pythonw -c "import subprocess, sys, os, threading, time; exec(open('run_all.py').read())"
python run_all.py
