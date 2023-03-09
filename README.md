# climate_analyzer

This project began as a desire visualize LOCAL climate change.
In the search for HARD DATA, I was surprised to find very little.
Yes, there are Big Institutions that are working on climate models.
Are they open source? Are they easy to interact with?
Does it answer the question how climate change affects me LOCALLY?
Maybe they exist, but I couldn't find any.  The idea of this app is 
to pull publically available NOAA climate data off the web and link
it to a visualization gui.

Command Line Script to:  
1. Download NOAA Climate Daily Summary Data  
2. Store in off-line database(s) organized by NOAA Weather Station  
3. Visualize with tkinter + matplotlib GUI  

NOAA requires a token to utilize their automated download fascility.
This token must be supplied to this app via an ini-file: cda.ini.  See:
  https://www.ncdc.noaa.gov/cdo-web/token

In order to download a station's climate data, the station ID must be specified.
NOAA has 100's (1000's) of weather stations spread across the country.
Each is assigned an ID, such as: 'GHCND:USW00024233'
This app supports searching for station ID based on a geographical region.

Geographical Regions are specified by fip_code. See:
  https://www.census.gov/library/reference/code-lists/ansi.html

Command line options to assist in station ID determination:  
* findrgn [2_letter_state]    : set fip_code used by find
* find    [radius]            : list all stations within region set by findrgn
* home    [lat/long]          : set location that station distance is measured from

From Command Line:  
    py -m cda [-option] [-arg]  

When installed with pip, it will add a 'cda.exe' file to your Python Environment
in the pythonXX\Scripts directory and a climate_analysis package in your
pythonXX\Lib\site-packages.  cda.exe utilizes the climate_analysis package.
Config data is kept in cda.ini, also stored in pythonXX\Lib\site-packages.
IS THERE SOMEPLACE BETTER?

The downloaded climate data is [tmin, tmax, tavg, prcp, show, snwd].  It is
organized by date, and <station_alias>.  <station_alias> is user defined, 
corresponds with a NOAA <station_id>, and also matches a sqlite db file name.
All db files are stored in a single directory, specified in cda.ini.

Collaborators are welcomed.  This could morph into a substantial project or
it could fizzle out. If interested, contact me: davidc@clearfocusengineering.com.
We can work out how to collaborate to move ths project forward.

