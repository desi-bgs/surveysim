import numpy as np
import astropy.io.fits as pyfits
from astropy.time import Time
from pkg_resources import resource_filename
from surveysim.utils import radec2altaz, mjd2lst
from operator import itemgetter

Lat_KPNO_deg = 31.0 + (57.0 + 50.3/60.0)/60.0

class surveyPlan:
    
    def __init__(self):
    # Read list of DESI tiles
    # Format of prototype file:
    # name:
    #     ['TILEID', 'RA', 'DEC', 'PASS', 'IN_DESI', 'EBV_MED', 'AIRMASS', 'EXPOSEFAC', 'STAR_DENSITY', 'PROGRAM', 'OBSCONDITIONS']
    # format:
    #     ['J', 'D', 'D', 'I', 'I', 'E', 'E', 'E', 'E', '6A', 'I']
    # unit:
    #     ['', '', '', '', '', '', '', '', '']
    # null:
    #     ['', '', '', '', '', '', '', '', '']
    # bscale:
    #     ['', '', '', '', '', '', '', '', '']
    # bzero:
    #     ['', '', '', '', '', '', '', '', '']
    # disp:
    #     ['', '', '', '', '', '', '', '', '']
    # start:
    #     ['', '', '', '', '', '', '', '', '']
    # dim:
    #     ['', '', '', '', '', '', '', '', '']
        hdulist0 = pyfits.open(resource_filename('surveysim', 'data/desi-tiles.fits'))
        tiledata = hdulist0[1].data
        tileID = tiledata.field('TILEID')
        RA = tiledata.field('RA')
        DEC = tiledata.field('DEC')
        Pass = tiledata.field('PASS')
        InDESI = tiledata.field('IN_DESI')
        Ebmv = tiledata.field('EBV_MED')
        AM = tiledata.field('AIRMASS')
        expFac = tiledata.field('EXPOSEFAC')
        starDensity = tiledata.field('STAR_DENSITY')
        program = tiledata.field('PROGRAM')
        obsconds = tiledata.field('OBSCONDITIONS')
        obstime = tiledata.field('OBSTIME')
        HA = tiledata.field('HA')
        hdulist0.close()

        self.tileID = tileID.compress((InDESI==1).flat) #Assuming 0=out, 1=in
        self.RA = RA.compress((InDESI==1).flat)
        self.DEC = DEC.compress((InDESI==1).flat)
        self.Pass = Pass.compress((InDESI==1).flat)
        self.Ebmv = Ebmv.compress((InDESI==1).flat)
        self.maxExpLen = 2.0 * obstime.compress((InDESI==1).flat) # This assumes bright time program
        self.starDensity = starDensity.compress((InDESI==1).flat)
        self.program = program.compress((InDESI==1).flat)
        self.obsconds = obsconds.compress((InDESI==1).flat)
        LST = self.RA + HA.compress((InDESI==1).flat)
        self.LSTmin = LST - 15.0
        for i in range(len(self.LSTmin)):
            if self.LSTmin[i] < 0.0:
                self.LSTmin[i] += 360.0
            elif self.LSTmin[i] >360.0:
                self.LSTmin[i] -= 360.0
        self.LSTmax = LST + 15.0
        for i in range(len(self.LSTmax)):
            if self.LSTmax[i] < 0.0:
                self.LSTmax[i] += 360.0
            elif self.LSTmax[i] > 360.0:
                self.LSTmax[i] -= 360.0

        self.status = np.zeros(len(self.tileID))
        self.priority = np.zeros(len(self.tileID))
        # Assign priority only as a function of DEC
        for i in range(len(self.priority)):
            dec = self.DEC[i]
            if dec <= -15.0:
                priority = 1
            elif dec > -15.0 and dec <= 0.0:
                priority = 2
            elif dec > 0.0 and dec <= 15.0:
                priority = 3
            elif dec > 15.0 and dec <= 30.0:
                priority = 4
            elif dec > 30.0 and dec <= 45.0:
                priority = 5
            elif dec > 45.0 and dec <= 60.0:
                priority = 6
            elif dec > 60.0 and dec < 75.0:
                priority = 7
            else:
                priority = 8
            self.priority[i] = priority

        # Dummy initialization: this is just to declare the class members
        self.moonUp = 'BRIGHT'
        self.LST_dark1_begin = -1.0
        self.LST_dark1_end = -1.0
        self.LST_dark2_begin = -1.0
        self.LST_dark2_end = -1.0

    # Checks whether that part of the night is dark or not.
    def isItDark(self, lst):
        if ( (self.LST_dark1_begin > 0.0 and self.LST_dark1_begin < lst and
              self.LST_dark1_end > 0.0 and lst < self.LST_dark1_end) or
             (self.LST_dark2_begin > 0.0 and self.LST_dark2_begin < lst and
              self.LST_dark2_end > 0.0 and lst < self.LST_dark2_end) ):
            brightness = 'DARK'
        else:
            brightness = self.moonUp
        return brightness

    # Sets the dark times times for this night and determines whether the rest is bright or grey.
    def getDarkTimes(self, day_stats):
        self.LST_dark2_begin = -1.0
        self.LST_dark2_end = -1.0
        if day_stats['MJDmoonrise'] > 0.0 and day_stats['MJDmoonrise'] > 0.0: # Moon rises and sets tonight
            if day_stats['MJDmoonrise'] < day_stats['MJDetwi']: # Moon is up by the end of twilight
                if day_stats['MJDmoonset'] < day_stats['MJDmtwi']: # Moon sets during the night
                    self.LST_dark1_begin = mjd2lst(day_stats['MJDmoonset'])
                    self.LST_dark1_end = mjd2lst(day_stats['MJDmtwi'])
                else: # Moon is always up
                    self.LST_dark1_begin = -1.0
                    self.LST_dark1_end = -1.0
            else: # Moon is down at the end of twilight
                self.LST_dark1_begin = mjd2lst(day_stats['MJDetwi'])
                if day_stats['MJDmoonrise'] < day_stats['MJDmtwi']:
                    self.LST_dark1_end = mjd2lst(day_stats['MJDmoonrise'])
                    if day_stats['MJDmoonset'] < day_stats['MJDmtwi']: # Second portion of dark time.
                        self.LST_dark2_begin = mjd2lst(day_stats['MJDmoonset'])
                        self.LST_dark2_end = mjd2lst(day_stats['MJDmtwi'])
                else:
                    self.LST_dark1_end = mjd2lst(day_stats['MJDmtwi'])
        elif day_stats['MJDmoonrise'] > 0.0 and day_stats['MJDmoonrise'] < 0.0: # Moon rises, but does not set
            if day_stats['MJDmoonrise'] < day_stats['MJDetwi']: # Moon is already up at end of twilight
                self.LST_dark1_begin = -1.0
                self.LST_dark1_end = -1.0
            else:
                self.LST_dark1_begin = day_stats['MJDetwi']
                self.LST_dark1_end = mjd2lst(day_stats['MJDmoonrise'])
        elif day_stats['MJDmoonrise'] < 0.0 and day_stats['MJDmoonrise'] > 0.0: # Moon doesn't rise, but sets
            if day_stats['MJDmoonset'] > 0.0 and day_stats['MJDmoonset'] < day_stats['MJDmtwi']:
                self.LST_dark1_begin = mjd2lst(day_stats['MJDmoonset'])
                self.LST_dark1_end = mjd2lst(day_stats['MJDmtwi'])
            else:
                self.LST_dark1_begin = -1.0
                self.LST_dark1_end = -1.0
        else: # Moon doesn't rise or set during the night
            self.LST_dark_begin = mjd2lst(day_stats['MJDetwi'])
            self.LST_dark_end = mjd2lst(day_stats['MJDmtwi'])
        # Just use the elevation at local midnight:
        # will need to get elevation as a function of time.
        alt, az = radec2altaz(day_stats['MoonRA'], day_stats['MoonDEC'], mjd2lst(day_stats['MJDmidnight']))
        if day_stats['MoonFrac'] < 0.2 or (alt*day_stats['MoonFrac'] < 12.0):
            self.moonUp = 'GREY'
        else:
            self.moonUp = 'BRIGHT'


    def afternoonPlan(self, day_stats, tiles_observed):
        """
        All the file names are hard coded, so there is no need to
        have them as arguments to this function.  The output file
        name has format obsplanYYYYMMDD.fits .
        """

        # Update status
        nto = len(tiles_observed)
        for i in range(nto):
            j = np.where(self.tileID == tiles_observed['TILEID'][i])
            self.status[j] = tiles_observed['STATUS'][i]

        self.getDarkTimes(day_stats)
        planList0 = []

        for i in range(len(self.tileID)):
            if ( self.status[i] < 2 and
                ((self.isItDark(self.LSTmin[i]) == 'DARK' and self.isItDark(self.LSTmax[i]) == 'DARK' and self.program[i] == 'DARK') or
                 ((self.isItDark(self.LSTmin[i]) != 'DARK' or self.isItDark(self.LSTmax[i]) != 'DARK') and self.program[i] != 'DARK')) ):
                planList0.append((self.tileID[i], self.RA[i], self.DEC[i], self.Ebmv[i], self.LSTmin[i], self.LSTmax[i],
                                 self.maxExpLen[i], self.priority[i], self.status[i], self.program[i], self.obsconds[i]))

        planList = sorted(planList0, key=itemgetter(7), reverse=True)
        cols = np.rec.array(planList,
                            names = ('TILEID', 'RA', 'DEC', 'EBV_MED', 'LSTMIN', 'LSTMAX', 'MAXEXPLEN', 'PRIORITY', 'STATUS', 'PROGRAM', 'OBSCONDITIONS'),
                            formats = ['i4', 'f8', 'f8', 'f8', 'f4', 'f4', 'f4', 'i4', 'i4', 'a6', 'i2'])

        tbhdu = pyfits.BinTableHDU.from_columns(cols)

        prihdr = pyfits.Header()
        prihdr['MOONFRAC'] = day_stats['MoonFrac']
        prihdr['MOONRA  '] = day_stats['MoonRA']
        prihdr['MOONDEC '] = day_stats['MoonDEC']
        prihdu = pyfits.PrimaryHDU(header=prihdr)
        filename = 'obsplan' + day_stats['dirName'] + '.fits'
        thdulist = pyfits.HDUList([prihdu, tbhdu])
        thdulist.writeto(filename, clobber=True)

        tilesTODO = len(planList)

        return tilesTODO, filename

