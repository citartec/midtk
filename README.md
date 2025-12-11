MidTk - A Python-based MIDI controller GUI.

<img width="1256" height="665" alt="image" src="https://github.com/user-attachments/assets/bf220d8c-3526-4561-a93a-91c1e0f01f85" />

https://github.com/user-attachments/assets/b7568fcd-7d10-422b-a276-5920cdd2e831

Overview
--------
MidTk lets you build and customize your own MIDI controller using sliders, buttons, and radio button groups.
All elements can be resized, positioned, grouped, saved, and reloaded.
-
How to use
----------
Right click on the background to create, save, load, select midi port and lock controls. Another right click on the sliders, buttons, radio group and group boxes will bring up the midi options and group options. 

If you right click then click unlock controls, it will bring up resize options and you can move things around. 

Groups
-------
Group boxes are used to group sliders, buttons and radio buttons. While unlock controls is selected you can drag these boxes over a layout you want to group and then press "recompute members" to create a group and use "recompute members" any time you want to add things to the group. You can also Duplicate groups.

4.9 will now assign midi numbers as you build your scenes. This saves a lot of time when building. 

Requirements
------------

Python 3.11.13

pip install mido

pip install python-rtmidi

Then run the python file,

python3 MidTk0.4.5.py


------- how to run on windows -------

 https://www.geeksforgeeks.org/installation-guide/how-to-install-conda-in-windows/ (this is like a walled garden that protects your core system)

open conda and input each line and press enter. 

conda create --name midtk python=3.11

pip install mido

pip install python-rtmidi

python MidTk0.4.9.py

press enter

(make sure you have the correct location of the MidTk0.4.9.py [drag it into the conda window]) 

To use the midtk interface on the same machine to control Ableton Live you will need an internal router like 
https://www.tobias-erichsen.de/software/loopmidi.html
