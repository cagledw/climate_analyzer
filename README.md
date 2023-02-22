# Climate Data Analysis

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

Geographical Regions are specified fip_code. See:
  https://www.census.gov/library/reference/code-lists/ansi.html

Command line options to assist in station ID determination:
    -findrgn [2_letter_state]    : set fip_code used by find 
    -find    [radius]            : list all stations within region set by findrgn
    -home    [lat/long]          : set location that station distance is measured from

From Command Line:
    py -m cda [-option] [-arg]
