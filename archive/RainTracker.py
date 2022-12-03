''' Estimates SS Primary Insurance Amount(PIA),
                 Maximum Family Benefit (MFB),
                 Retirement Benefit Amount (RBA)
    Given a Birth Date and Wage History (in CSV File)

'''
import re
import csv
import numpy as np
# from collections  import defaultdict, namedtuple

from datetime import date, datetime

import matplotlib.pyplot as mpl
import matplotlib.ticker as ticker
from guiMain     import guiMain # GuiEvent, GuiEquityPrice , GuiWindowID, GuiEventType,

STATIONS = ['USW00024233', 'US1WAKG0225']


def is_leap_year(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)

def date2enum(year, month, day):
    mm2days = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return sum(mm2days[:month-1]) + day-1

def GetWeather(weather_file):
    """ Returns a dict, keyed by year.  Each item in dict is 366-item np array.
    """

    station = None
    np_flds = {'DATE': (np.uint16,3),
               'PRCP': (np.float32),
               'TAVG': (np.int16),
               'TMAX': (np.int16),
               'TMIN': (np.int16)}
    other_flds = ['STATION', 'NAME', 'SNOW', 'SNWD']

    np_dtype = np.dtype([(k,v) for k,v in np_flds.items()])
    weather_dict = {}

    with open(weather_file, mode='r') as csvfile:
        reader = csv.DictReader(csvfile)
        hdr_diff = set(np_flds.keys()) - set(reader.fieldnames)
        if hdr_diff:
            raise ValueError(f'CSV {weather_file} missing: {hdr_diff}')

        for row in reader:
            if station is None:
                station = row['STATION']
            elif station != row['STATION']:
                raise ValueError

            dtup = datetime.strptime(row['DATE'], "%Y-%m-%d").timetuple()
            if dtup.tm_year not in weather_dict.keys():
                weather_dict[dtup.tm_year] = np.zeros(366, dtype = np_dtype)

            yr_m_day = (dtup.tm_year, dtup.tm_mon, dtup.tm_mday)
            weather_dict[int(dtup.tm_year)][date2enum(*yr_m_day)] = \
              (yr_m_day,
               np.float32(row['PRCP'] if row['PRCP'] else 0.0),
               np.int16(row['TAVG'] if row['TAVG'] else np.iinfo(np.int16).min),
               np.int16(row['TMAX'] if row['TMAX'] else np.iinfo(np.int16).max),
               np.int16(row['TMIN'] if row['TMIN'] else np.iinfo(np.int16).min))


    return {station: dict(weather_dict)}


def PlotRain(weather_data):
    # for day in range(58,60):
    #     print(day)
    #     for _yr in weather_data.keys():
    #         print(weather_data[_yr][day]['DATE'], weather_data[_yr][day]['PRCP'])

    mpl.rc('axes',   grid         = True)
    mpl.rc('axes',   titlesize    = 12)
    mpl.rc('xtick',  labelsize    = 8)
    mpl.rc('ytick',  labelsize    = 8)
    mpl.rc('legend', fontsize     = 8)
    mpl.rc('legend', labelspacing = 0.25)
    mpl.rc('lines',  linewidth=0.7)

    fig  = mpl.figure(figsize = (9,6), tight_layout = True)
    ax1   = fig.add_subplot(1,1,1)
    # ax2   = fig.add_subplot(2,1,2)
    # fig.suptitle(title, fontsize = 8)

    # ax1.plot(weather_data[2022]['PRCP'])
    for yr, data in weather_data.items():
        if yr not in [2021, 2022]:
            continue

        print(yr, len(data['PRCP']))
        ax1.plot(data['PRCP'])

#     pdat = list(zip(*date_rba_pair)) #pdat[0] = dates, pdat[1] = rba
#     rba  = np.asarray(pdat[1])
#     ax1.plot(pdat[0], pdat[1], marker='s', markersize = 2)
#     ax1.set_ylabel('Retirement Benefit Amount $/month')

#     pdat2 = list(zip(*rba_increase)) #pdat2[0] = dates, pdat[1] = d_rba
#     d_rba = np.asarray(pdat2[1])
#     ax2.plot(pdat2[0], d_rba, marker='s', markersize = 2)
#     ax2.set_ylabel('Y2Y % Increase')

#     ticks = [datetime.date(year = year, month = 1, day = 1) for
#              year in range(min(pdat[0]).year, max(pdat[0]).year + 2)]

#     ax1.set_xlim(left = ticks[0], right = ticks[-1])
#     ax2.set_xlim(left = ticks[0], right = ticks[-1])

    mpl.show()


# def SSCalc(birth_date, wages_dict):
#     RetireAge = recordclass('RetireAge', 'yr mo')

#     sorted_years = sorted(wages_dict.keys())
#     year_first = sorted_years[0]
#     year_last  = sorted_years[-1]
#     for yr in range(year_first, year_last + 1, 1):
#         try: yr_wage = wages_dict[yr]
#         except: yr_wage = 0

#     sex          = '0'
#     ssn          = '000000000'
#     benefit_type = 1
#     bday_month = int(birth_date[:2])
#     bday_year  = int(birth_date[-4:])
#     retire_age = RetireAge(yr = 62, mo = 1)

#     date_rba_pair = []
#     while retire_age.yr < 70 or retire_age.mo <= 0:

#         calc_year = bday_year + retire_age.yr
#         calc_month = bday_month + retire_age.mo
#         if calc_month > 12:
#             calc_month -= 12
#             calc_year  += 1
#         calc_date = datetime.date(year = calc_year, month = calc_month, day = 1)

#         with open(PIAFILE, mode='w') as _calcdata:
#             _calcdata.write('01' + ssn + sex + birth_date + '\n')
#             _calcdata.write('03{0:1d}{1:02d}{2:4}\n'.format(benefit_type, calc_month, calc_year))
#             _calcdata.write('06{0}{1}\n'.format(year_first, year_last))
#             _calcdata.write('16FakeName\n')
#             _calcdata.write('17FakeAddress\n')
#             _calcdata.write('20' + '0' * (year_last - year_first + 1) + '\n')

#             year = year_first
#             for linenum in range(22,29,1):

#                 wages = []
#                 for i in range(10):
#                     if year > year_last:
#                         break

#                     try: wages.append('{:10.2f}'.format(wages_dict[year]))
#                     except: break
#                     year += 1

#                 _calcdata.write('{:2d} '.format(linenum) +
#                                 ' '.join(['{}'.format(val) for val in wages]) +
#                                 '\n')

#                 if year > year_last:
#                     break

#             _calcdata.write('402021551' + '\n')

#         running_proc = Popen(['anypiac.exe'], stdout=PIPE, stdin=PIPE, stderr=PIPE)
#         out, err = running_proc.communicate(input = PIAFILE.encode())

#         ok = re.match(EXPECTED_ANYPIA_OUPUT, out.decode())
#         if not ok:
#             raise exception('Unexpected ANYPIA OUTPUT')

#         result = GetResult(ANYPIA_OUTFILE)
#         date_rba_pair.append((calc_date, float(result['rba'])))

#         retire_age.mo += 1
#         if retire_age.mo >= 12:
#             retire_age.mo = 0
#             retire_age.yr += 1

#     return date_rba_pair

import argparse

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='PlotRain')
    parser.add_argument('-datfile', action='store', help='birthday', default = 'noaa_seatac.csv')
    args = parser.parse_args()

    # station, weather_data = GetWeather(args.datfile)
    # PlotRain(weather_data)

    gui = guiMain(GetWeather(args.datfile), (1000, 100))  # Gui Setup
    # gui.plot(*GetWeather(args.datfile))
    # gui.plot(station, weather_data)
    gui.mainloop()
