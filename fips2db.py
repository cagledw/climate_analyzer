"""
Climate Data Analysis.
  Download Data from NOAA Climate Data WebSite and/or Launch tkinter GUI
  Only Climate Data for locations this Apps's Configuration (*.ini) File can be downloaded

  Three options for Climate Data Download:
    -find_ids : Display Stations and their ID within certain distance of 'Home'
    -show_ids : Display Stations whose ID is known
    -getcd    : download Historical Climate Data for specific Station to sqlite DB

  Otherwise, launches GUI for analysis of data previously stored in sqlite DB.


"""

import re
import os

from glob import glob

from dbCoupler import dbCoupler, DBTYPE_FIP

user_dbPath = 'AppData\\ClimateData'

StateAbrev = {'Alabama':             'AL',            
              'Alaska':              'AK',
              'Arizona':             'AZ',            
              'Arkansas':            'AR',         
              'California':          'CA',         
              'Colorado':            'CO',        
              'Connecticut':         'CT',        
              'Delaware':            'DE',       
              'DistrictofColumbia':  'DC',
              'Florida':             'FL', 
              'Georgia':             'GA', 
              'Hawaii':              'HI',
              'Idaho':               'ID', 
              'Illinois':            'IL',  
              'Indiana':             'IN',
              'Iowa':                'IA', 
              'Kansas':              'KS', 
              'Kentucky':            'KY', 
              'Louisiana':           'LA',
              'Maine':               'ME',
              'Maryland':            'MD', 
              'Massachusetts':       'MA', 
              'Michigan':            'MI', 
              'Minnesota':           'MN', 
              'Mississippi':         'MS', 
              'Missouri':            'MO', 
              'Montana':             'MT', 
              'Nebraska':            'NE', 
              'Nevada':              'NV', 
              'NewHampshire':        'NH', 
              'NewJersey':           'NJ', 
              'NewMexico':           'NM', 
              'NewYork':             'NY', 
              'NorthCarolina':       'NC', 
              'NorthDakota':         'ND', 
              'Ohio':                'OH', 
              'Oklahoma':            'OK',
              'Oregon':              'OR',
              'Pennsylvania':        'PA', 
              'RhodeIsland':         'RI', 
              'SouthCarolina':       'SC', 
              'SouthDakota':         'SD', 
              'Tennessee':           'TN', 
              'Texas':               'TX', 
              'Utah':                'UT', 
              'Vermont':             'VT', 
              'Virginia':            'VI', 
              'Washington':          'WA', 
              'WestVirginia':        'WV', 
              'Wisconsin':           'WI', 
              'Wyoming':             'WY'} 

def fips2db(fsrc, dbfName):

    with open(fsrc, 'r') as rfp:
        src_lines = rfp.readlines()
    rfp.close()

    fipList = []
    QTypes = ['County', 'Parish', 'City', 'city','Borough', 'Area', 'Park'] 
    fip_1st2 = None
    mobj = re.compile('^\s+(\d{5})\s*(\S*)\s?(\S*)\s?(\S*)\s?(\S*)') 
    for _lcnt, _line in enumerate(src_lines):
        found = mobj.match(_line)

        fip_code = found.group(1)
        region = found.group(2)
        qualifier = None

        if len(found.group(3)) == 0:
            if (fip_code[2:] != '000'):
                print(f'Ignore {fip_code} {region}')
                continue
            qualifier = 'State'      

        elif found.group(3) in QTypes:
            qualifier = found.group(3)

        elif found.group(4) in QTypes:
            region += found.group(3)
            qualifier = found.group(4)

        elif found.group(5) in QTypes:
            region += found.group(4)
            qualifier = found.group(5)

        else:
            region += found.group(3) + found.group(4)
            qualifier = 'State'

            if (fip_code[2:] != '000'):
                print(f'Ignore {fip_code} {region}')
                continue

        if fip_1st2 != fip_code[:2]:
            fip_1st2 = fip_code[:2]
            state_abrev = StateAbrev[region]

        fipList.append(DBTYPE_FIP(code = fip_code,
                                  state = state_abrev,
                                  region = region,
                                  qualifier = qualifier))

    dbMgr = dbCoupler()
    dbMgr.open(dbfName)
    dbMgr.wr_fiptable('FIP_CODES', fipList)
    dbMgr.close()

if __name__ == '__main__':

    import argparse
    parser = argparse.ArgumentParser(description='  \033[32mConvert Text File of FIPS Codes to SQLite DB\n'
                                                 '  -config   to display configured stations in ini-file\033[37m',
                                                 formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('fsrc', nargs=1)
    parser.add_argument('fdst', nargs=1)
    
    args = parser.parse_args()
    fips2db(args.fsrc[0], args.fdst[0])
    # args = parser.parse_args()

