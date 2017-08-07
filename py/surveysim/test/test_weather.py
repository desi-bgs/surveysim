import unittest
import datetime
import tempfile
import shutil
import os

import numpy as np

import astropy.time

import desisurvey.config

from surveysim.weather import Weather


class TestWeather(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Create a temporary directory.
        cls.tmpdir = tempfile.mkdtemp()
        # Write output files to this temporary directory.
        config = desisurvey.config.Configuration()
        config.set_output_path(cls.tmpdir)

    @classmethod
    def tearDownClass(cls):
        # Remove the directory after the test.
        shutil.rmtree(cls.tmpdir)
        # Reset our configuration.
        desisurvey.config.Configuration.reset()

    def setUp(self):
        start = datetime.date(2020, 1, 1)
        stop = datetime.date(2020, 3, 1)
        gen = np.random.RandomState(123)
        self.w = Weather(start, stop, gen=gen)

    def test_dome_open_prob(self):
        """Dome should be open 50-70% of the time in Jan-Feb"""
        n_nights = self.w.num_nights
        self.assertEqual(n_nights, 31 + 29) # 2020 is a leap year!
        open_nights = np.count_nonzero(
            self.w._table['open'][::self.w.steps_per_day])
        open_frac = open_nights / float(n_nights)
        self.assertTrue(0.5 < open_frac < 0.7)

    def test_same_seed(self):
        """Weather should be identical with same seed"""
        gen = np.random.RandomState(123)
        w = Weather(self.w.start_date, self.w.stop_date, gen=gen)
        for name in w._table.colnames:
            self.assertTrue(np.all(self.w._table[name] == w._table[name]))

    def test_different_seed(self):
        """Weather should be different with different seed"""
        gen = np.random.RandomState(1234)
        w = Weather(self.w.start_date, self.w.stop_date, gen=gen)
        for name in w._table.colnames:
            self.assertTrue(name == 'mjd' or
                            np.any(self.w._table[name] != w._table[name]))

    def test_get(self):
        """The get() method should return nearest time in mjd column"""
        table = self.w._table
        t_step = table['mjd'][1] - table['mjd'][0]
        dt = np.random.uniform(-0.49 * t_step, 0.49 * t_step, size=len(table))
        when = astropy.time.Time(table['mjd'] + dt, format='mjd')
        for i in range(1, len(table) - 1):
            row = self.w.get(when[i])
            self.assertEqual(row['mjd'], table[i]['mjd'])

    def test_get_multiple(self):
        """The get() method can be called with one or multiple times."""
        table = self.w._table
        mjd = table['mjd'][10]
        row = self.w.get(astropy.time.Time(mjd, format='mjd'))
        self.assertTrue(0. <= row['transparency'] <= 1.)
        rows = self.w.get(astropy.time.Time([mjd] * 5, format='mjd'))
        self.assertTrue(len(rows) == 5)
        for i in range(5):
            self.assertTrue(0. <= rows['transparency'][i] <= 1.)

    def test_save_restore(self):
        """Save and restore a weather file"""
        self.w.save('weather.fits')
        w = Weather(restore='weather.fits')
        for name in w._table.colnames:
            self.assertTrue(np.all(self.w._table[name] == w._table[name]))
        self.assertEqual(self.w._table.meta['START'], w._table.meta['START'])
        self.assertEqual(self.w._table.meta['STOP'], w._table.meta['STOP'])
        self.assertEqual(self.w._table.meta['NIGHTS'], w._table.meta['NIGHTS'])
        self.assertEqual(self.w._table.meta['STEPS'], w._table.meta['STEPS'])


def test_suite():
    """Allows testing of only this module with the command::
        python setup.py test -m <modulename>
    """
    return unittest.defaultTestLoader.loadTestsFromName(__name__)