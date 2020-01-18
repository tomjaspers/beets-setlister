# Copyright 2015, Tom Jaspers <contact@tomjaspers.be>.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.

"""Generates playlists from setlist.fm
https://github.com/tomjaspers/beets-setlister
"""

from __future__ import (division, absolute_import, print_function,
                        unicode_literals)

from beets.plugins import BeetsPlugin
from beets import ui
from beets.library import Item
from beets.dbcore.query import AndQuery, OrQuery, MatchQuery
from beets.util import mkdirall, normpath, syspath
import beets.autotag.hooks as hooks
import os
import requests

import subprocess


def _get_best_match(items, track_name, artist_name):
    """ Returns the best match (according to a track_name/artist_name distance)
    from a list of Items
    """

    def calc_distance(track_info, track_name, artist_name):
        dist = hooks.Distance()

        dist.add_string('track_title', track_name, track_info.title)

        if track_info.artist:
            dist.add_string('track_artist',
                            artist_name,
                            track_info.artist)

        return dist.distance

    matches = [(i, calc_distance(i, track_name, artist_name)) for i in items]
    matches.sort(key=lambda match: match[1])

    return matches[0]


def _get_mb_candidate(track_name, artist_name, threshold=0.2):
    """Returns the best candidate from MusicBrainz for a track_name/artist_name
    """
    candidates = hooks.item_candidates(Item(), artist_name, track_name)
    best_match = _get_best_match(candidates, track_name, artist_name)

    return best_match[0] if best_match[1] <= threshold else None


def _find_item_in_lib(lib, track_name, artist_name):
    """Finds an Item in the library based on the track_name.

    The track_name is not guaranteed to be perfect (i.e. as soon on MB),
    so in that case we query MB and look for the track id and query our
    lib with that.
    """

    # todo: sometimes returns matches by other artists when requested artist has no matching tracks

    # Query the library based on the track name
    query = MatchQuery('title', track_name)
    lib_results = lib._fetch(Item, query=query)

    # Maybe the provided track name isn't all too good  todo: fails e.g. for Opeth - Reverie/Harlequin Forest due to mismatch in `/`
    # Search for the track on MusicBrainz, and use that info to retry our lib
    if not lib_results:
        mb_candidate = _get_mb_candidate(track_name, artist_name)
        if mb_candidate:
            query = OrQuery((
                        AndQuery((
                            MatchQuery('title', mb_candidate.title),
                            MatchQuery('artist', mb_candidate.artist),
                        )),
                        MatchQuery('mb_trackid', mb_candidate.track_id)
                    ))
            lib_results = lib._fetch(Item, query=query)

    if not lib_results:
        return None

    # If we get multiple Item results from our library, choose best match
    # using the distance
    if len(lib_results) > 1:
        return _get_best_match(lib_results, track_name, artist_name)[0]

    return lib_results[0]


def _save_playlist(m3u_path, items):
    """Saves a list of Items as a playlist at m3u_path
    """
    mkdirall(m3u_path)
    with open(syspath(m3u_path), 'w') as f:
        for item in items:
            f.write(item.path.decode('utf-8') + u'\n')


# Reference: https://api.setlist.fm/docs/1.0/resource__1.0_search_setlists.html
SETLISTFM_ENDPOINT = 'https://api.setlist.fm/rest/1.0/search/setlists'

def _get_setlist(session, artist_name, date=None):
    """Query setlist.fm for an artist and return the first
    complete setlist, alongside some information about the event
    """
    venue_name = None
    event_date = None
    track_names = []

    # Query setlistfm using the artist_name
    response = session.get(SETLISTFM_ENDPOINT, params={
               'artistName': artist_name,
               'date': date,
               })

    if not response.status_code == 200: 
        return

    # Setlist.fm can have some events with empty setlists
    # We'll just pick the first event with a non-empty setlist
    results = response.json()
    setlists = results['setlist']
    if not isinstance(setlists, list):
        setlists = [setlists]
    for setlist in setlists:
        sets = setlist['sets']
        if len(sets) > 0:
            artist_name = setlist['artist']['name']
            event_date = setlist['eventDate']
            venue_name = setlist['venue']['name']
            for subset in sets['set']:
                for song in subset['song']:
                    track_names += [song['name']]
            break  # Stop because we have found a setlist

    return {'artist_name': artist_name,
            'venue_name': venue_name,
            'event_date': event_date,
            'track_names': track_names}


class SetlisterPlugin(BeetsPlugin):
    def __init__(self):
        super(SetlisterPlugin, self).__init__()
        self.config.add({
            'playlist_dir': None,
            'api_key': '',
        })

        if not os.path.isdir(os.path.expanduser(self.config['playlist_dir'].get(str))):
            self._log.warning(u'You have to configure a valid `playlist_dir`')
            return

        if not self.config['api_key']:
            self._log.warning(u'You have to provide your setlist.fm API key. Request a key at https://www.setlist.fm/settings/apps and configure it as `api_key` as `api_key`')
            return


        self.session = requests.Session()
        self.session.headers = {
            'Accept': 'application/json',
            'User-Agent': 'beets',
            'x-api-key': self.config['api_key'].get(str)
        }

    def setlister(self, lib, artist_name, date=None, play=False):
        """Glue everything together
        """

        # Support `$ beet setlister red hot chili peppers`
        if isinstance(artist_name, list):
            artist_name = ' '.join(artist_name)

        if not artist_name:
            self._log.warning(u'You have to provide an artist')
            return

        # Extract setlist information from setlist.fm
        try:
            setlist = _get_setlist(self.session, artist_name, date)
        except Exception:
            self._log.info(u'error scraping setlist.fm for {0}'.format(
                            artist_name))
            return

        if not setlist or not setlist['track_names']:
            self._log.info(u'could not find a setlist for {0}'.format(
                           artist_name))
            return

        setlist_name = u'{0} at {1} ({2})'.format(
                        setlist['artist_name'],
                        setlist['venue_name'],
                        setlist['event_date'])

        self._log.info(u'Setlist: {0} ({1} tracks)'.format(
                        setlist_name, len(setlist['track_names'])))

        # Match the setlist' tracks with items in our library
        items, _ = self.find_items_in_lib(lib,
                                          setlist['track_names'],
                                          artist_name)

        # Save the items as a playlist
        m3u_path = normpath(os.path.join(
                                self.config['playlist_dir'].as_filename(),
                                setlist_name + '.m3u'))

        _save_playlist(m3u_path, items)
        self._log.info(u'Saved playlist at "{0}"'.format(m3u_path.decode('utf-8')))

        if play:
            # todo: Double check whether this is sensible ~ beets documentation (it probably isn't)
            subprocess.Popen(['xdg-open', m3u_path.decode('utf-8')])

    def find_items_in_lib(self, lib, track_names, artist_name):
        """Returns a list of items found, and list of items not found in library
        from a given list of track names.
        """
        items, missing_items = [], []
        for track_nr, track_name in enumerate(track_names):
            item = _find_item_in_lib(lib, track_name, artist_name)
            if item:
                items += [item]
                message = ui.colorize('text_success', u'found')
            else:
                missing_items += [item]
                message = ui.colorize('text_error', u'not found')
            self._log.info("{0} {1}: {2}".format(
                          (track_nr+1), track_name, message))
        return items, missing_items

    def commands(self):
        def func(lib, opts, args):
            self.setlister(lib, ui.decargs(args), opts.date, opts.play)

        cmd = ui.Subcommand(
            'setlister',
            help='create playlist from an artists\' latest setlist'
        )
        cmd.parser.add_option('-d', '--date', dest='date', default=None,
                              help='setlist of a specific date (dd-MM-yyyy)')
        cmd.parser.add_option('-p', '--play', action='store_true',
                              help='play the playlist (boolean)')

        cmd.func = func

        return [cmd]
