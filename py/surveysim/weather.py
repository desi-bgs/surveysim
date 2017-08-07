"""Simulate weather conditions affecting observations.
"""
from __future__ import print_function, division, absolute_import

from datetime import datetime

import numpy as np

import astropy.time
import astropy.table
import astropy.units as u

import desiutil.log

import desimodel.weather

import desisurvey.config
import desisurvey.utils


class Weather(object):
    """Simulate weather conditions affecting observations.

    Seeing and transparency values are stored with 32-bit floats to save
    some memory.

    Parameters
    ----------
    start_date : datetime.date or None
        Survey starts on the evening of this date. Use the ``first_day``
        config parameter if None (the default).
    stop_date : datetime.date or None
        Survey stops on the morning of this date. Use the ``last_day``
        config parameter if None (the default).
    time_step : astropy.units.Quantity
        Time step for calculating updates. Must evenly divide 24 hours.
    gen : numpy.random.RandomState or None
        Random number generator to use for reproducible samples. Will be
        initialized (un-reproducibly) if None.
    restore : filename or None
        Restore an existing weather simulation from the specified file name.
        All other parameters are ignored when this is provided. A relative path
        name refers to the :meth:`configuration output path
        <desisurvey.config.Configuration.get_path>`.
    """
    def __init__(self, start_date=None, stop_date=None, time_step=5 * u.min,
                 gen=None, restore=None):
        self.log = desiutil.log.get_logger()
        config = desisurvey.config.Configuration()

        if restore is not None:
            self._table = astropy.table.Table.read(config.get_path(restore))
            self.start_date = desisurvey.utils.get_date(
                self._table.meta['START'])
            self.stop_date = desisurvey.utils.get_date(
                self._table.meta['STOP'])
            self.num_nights = self._table.meta['NIGHTS']
            self.steps_per_day = self._table.meta['STEPS']
            return

        if gen is None:
            self.log.warn('Will generate unreproducible random numbers.')
            gen = np.random.RandomState()

        # Use our config to set any unspecified dates.
        if start_date is None:
            start_date = config.first_day()
        if stop_date is None:
            stop_date = config.last_day()
        num_nights = (stop_date - start_date).days
        if num_nights <= 0:
            raise ValueError('Expected start_date < stop_date.')

        # Check that the time step evenly divides 24 hours.
        steps_per_day = int(round((1 * u.day / time_step).to(1).value))
        if not np.allclose((steps_per_day * time_step).to(u.day).value, 1.):
            raise ValueError(
                'Requested time_step does not evenly divide 24 hours: {0}.'
                .format(time_step))

        # Calculate the number of times where we will tabulate the weather.
        num_rows = num_nights * steps_per_day
        meta = dict(START=str(start_date), STOP=str(stop_date),
                    NIGHTS=num_nights, STEPS=steps_per_day)
        self._table = astropy.table.Table(meta=meta)

        # Initialize column of MJD timestamps.
        t0 = desisurvey.utils.local_noon_on_date(start_date)
        times = t0 + (np.arange(num_rows) / float(steps_per_day)) * u.day
        self._table['mjd'] = times.mjd

        # Decide whether the dome is opened on each night.
        # We currently assume this is fixed for a whole night, but
        # tabulate the status at each time so that this could be
        # updated in future to simulate partial-night weather outages.
        dome_closed_prob = desisurvey.utils.dome_closed_probabilities()
        self._table['open'] = np.ones(num_rows, bool)
        for i in range(num_nights):
            ij = i * steps_per_day
            month = times[ij].datetime.month
            if gen.uniform() < dome_closed_prob[month - 1]:
                self._table['open'][ij:ij + steps_per_day] = False

        # Generate a random atmospheric seeing time series.
        dt_sec = 24 * 3600. / steps_per_day
        self._table['seeing'] = desimodel.weather.sample_seeing(
            num_rows, dt_sec=dt_sec, gen=gen).astype(np.float32)

        # Generate a random atmospheric transparency time series.
        self._table['transparency'] = desimodel.weather.sample_transp(
            num_rows, dt_sec=dt_sec, gen=gen).astype(np.float32)

        self.start_date = start_date
        self.stop_date = stop_date
        self.num_nights = num_nights
        self.steps_per_day = steps_per_day

    def save(self, filename, overwrite=True):
        """Save the generated weather to a file.

        The saved file can be restored using the constructor `restore`
        parameter.

        Parameters
        ----------
        filename : str
            Name of the file where the weather should be saved. A
            relative path name refers to the :meth:`configuration output path
            <desisurvey.config.Configuration.get_path>`.
        overwrite : bool
            Silently overwrite any existing file when this is True.
        """
        config = desisurvey.config.Configuration()
        filename = config.get_path(filename)
        self._table.write(filename, overwrite=overwrite)
        self.log.info('Saved weather to {0}.'.format(filename))

    def get(self, time):
        """Get the weather conditions at the specified time(s).

        Returns the conditions at the closest tabulated time, rather than
        using interpolation.

        Parameters
        ----------
        time : astropy.time.Time
            Time(s) when the simulated weather is requested.

        Returns
        -------
        table slice
            Slice of precomputed table containing row(s) corresponding
            to the requested time(s).
        """
        offset = np.floor(
            (time.mjd - self._table['mjd'][0]) * self.steps_per_day + 0.5
            ).astype(int)
        if np.any(offset < 0) or np.any(offset > len(self._table)):
            raise ValueError('Cannot get weather beyond tabulated range.')
        return self._table[offset]
