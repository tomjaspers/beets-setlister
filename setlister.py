# This file is part of beets.
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


def _get_mb_candidate(track_name, artist_name):
    def calc_distance(track_info):
        dist = hooks.Distance()

        dist.add_string('track_title', track_name, track_info.title)

        if track_info.artist:
            dist.add_string('track_artist', artist_name, track_info.artist)

        return dist.distance

    candidates = hooks.item_candidates(Item(), artist_name, track_name)
    matches = [(c, calc_distance(c)) for c in candidates]
    matches.sort(key=lambda match: match[1])

    best_match = matches[0]

    return best_match[0] if best_match[1] <= 0.2 else None


def _find_item_in_lib(lib, track_name, artist_name):
    """Finds an Item in the library based on the track_name.

    The track_name is not guaranteed to be perfect (i.e. as soon on MB),
    so in that case we query MB and look for the track id and query our
    lib with that.
    """
    # Query the library based on the track name
    query = MatchQuery('title', track_name)
    lib_results = lib._fetch(Item, query=query)

    # Maybe the provided track name isn't all too good
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

    # TODO: Handle situation where lib_results might contain multiple Items
    return lib_results[0]


def _save_playlist(m3u_path, items):
    """Saves a list of Items as a playlist at m3u_path
    """
    mkdirall(m3u_path)
    with open(syspath(m3u_path), 'w') as f:
        for item in items:
            f.write(item.path + b'\n')


requests_session = requests.Session()
requests_session.headers = {'User-Agent': 'beets'}
SETLISTFM_ENDPOINT = 'http://api.setlist.fm/rest/0.1/search/setlists.json'


def _get_setlist(artist_name):
    """Query setlist.fm for an artist and return the first
    complete setlist, alongside some information about the event
    """
    venue_name = None
    event_date = None
    track_names = []

    # Query setlistfm using the artist_name
    response = requests_session.get(SETLISTFM_ENDPOINT, params={
               'artistName': artist_name,
               })

    # Setlist.fm can have some events with empty setlists
    # We'll just pick the first event with a non-empty setlist
    results = response.json()
    setlists = results['setlists']['setlist']
    for setlist in setlists:
        sets = setlist['sets']
        if len(sets) > 0:
            artist_name = setlist['artist']['@name']
            event_date = setlist['@eventDate']
            venue_name = setlist['venue']['@name']
            for subset in sets['set']:
                for song in subset['song']:
                    track_names += [song['@name']]
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
        })

    def setlister(self, lib, artist_name):
        """Glue everything together
        """
        if not self.config['playlist_dir']:
            self._log.warning(u'You have to configure a playlist_dir')
            return

        if isinstance(artist_name, list):
            artist_name = artist_name[0]

        if not artist_name:
            self._log.warning(u'You have to provide an artist')
            return

        # Extract setlist information from setlist.fm
        try:
            setlist = _get_setlist(artist_name)
        except Exception:
            self._log.debug(u'error scraping setlist.fm for {0}'.format(
                            artist_name))
            return

        if not setlist['track_names']:
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
        self._log.info(u'Saved playlist at "{0}"'.format(m3u_path))

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
        def create(lib, opts, args):
            self.setlister(lib, ui.decargs(args))

        setlist_cmd = ui.Subcommand(
            'setlister',
            help='create playlist from an artists\' latest setlist'
        )

        setlist_cmd.func = create

        return [setlist_cmd]
