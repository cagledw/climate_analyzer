# climate_analyzer

climate_analyzer is a command line app that downloads NOAA weather station 
daily summary data and provides a gui to analyze year-to-year trends.
It also provides for searching a particular region for available NOAA
weather stations. climate_analyzer uses NOAA's Web Services API described
here: ([https://www.ncdc.noaa.gov/cdo-web/webservices]).

## Features
1. Search for available NOAA weather stations by state/county.
2. Download NOAA Climate Daily Summary Data by weather station. 
3. Store data in off-line database(s) organized by weather station.
4. Visualize with tkinter + matplotlib GUI  
5. Checks NOAA Web Services for updates to existing off-line database(s).

## Usage
climate_analyzer is a command line app that takes one and only one option.
If no option is provided, climate_analyzer checks for updates to existing
databases and then launches the visualization gui.  In order to access NOAA's
Web Services, an access token must be obtained and provided to climate_analyzer.

When installed with pip, climate_analyzer will add 'cda.exe' to the Python
Environment in the pythonXX\Scripts directory and a climate_analysis package to
pythonXX\Lib\site-packages.  cda.exe utilizes the climate_analysis package.
Config data is kept in cda.ini, also stored in pythonXX\Lib\site-packages.
### Options

#### --token [access-token]
Set the <access-token> used by climate_analyzer when connecting to NOAA's
Web Services.  The <access-token> is a 32-character alpha-numeric and can be
obtained from here: https://www.ncdc.noaa.gov/cdo-web/token
This, and other configuration parameters are stored in
..\site-packages\climate_analyzer\cda.ini.

#### --findrgn [state]
Set the state & county region used by --find.  For each state, climate_analyzer
prompts with a list of possible counties (or parishes).  The state/county is
converted 5-digit fip_code and stored in cda.ini. See:
https://www.census.gov/library/reference/code-lists/ansi.html

#### --find [radius]
Display <STATION_ID> and other information for all weather stations within
the state & county set by -findrgn. 

#### --home [lat,long]
Set internal variable <HOME> used to calculate distance of weather station.

#### --station [alias]
Set <STATION_ALIAS> and <STATION_ID> used by --getcd.  The user is prompted
for the <STATION_ID>.  Any number of alias & id pairs may be set but a 
[alias, id] pair must be set inorder to download its climate data.

#### --getcd [alias]
Download all available daily summary climate data for [alias].  Daily summary
consists of [tmin, tmax, tavg, prcp, snow, snwd].  Data is stored in sqlite 
database @ %USERPROFILE%/AppData/ClimateData with a filename of [alias].  The
location used to store sqlite databases can be changed by editing cda.ini.

