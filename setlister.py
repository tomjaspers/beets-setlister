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
from beets.dbcore.query import MatchQuery
from beets.util import mkdirall, normpath, syspath
import os
import requests


def _find_item_in_lib(lib, track_name, artist_name=None):
    # Query the library based on the track name
    query = MatchQuery(field='title', pattern=track_name)
    lib_results = lib._fetch(Item, query=query)

    # Maybe the provided track name isn't all too good
    # Search for the track on MusicBrainz, and use that info to retry our lib
    if not lib_results:
        # TODO: Search track name on MusicBrainz
        mb_candidates = None
        if mb_candidates:
            pass

    if not lib_results:
        return None

    # TODO: Handle situation where lib_results might contain multiple Items
    return lib_results[0]

requests_session = requests.Session()
requests_session.headers = {'User-Agent': 'beets'}
SETLISTFM_ENDPOINT = 'http://api.setlist.fm/rest/0.1/search/setlists.json'


class SetlisterPlugin(BeetsPlugin):
    def __init__(self):
        super(SetlisterPlugin, self).__init__()
        self.config.add({
            'playlist_dir': u'~/Music/setlisttest',
        })

    def create_playlist(self, lib, artist_name):
        if isinstance(artist_name, list):
            artist_name = artist_name[0]

        # Query setlistfm using the artist_name
        response = requests_session.get(SETLISTFM_ENDPOINT, params={
            'artistName': artist_name,
            })

        # Extract setlist information from setlist.fm
        setlist_name = None
        setlist_tracks = []
        # Get results using JSON
        try:
            results = response.json()
            # Find the first proper setlist
            setlists = results['setlists']['setlist']
            for setlist in setlists:
                sets = setlist['sets']
                # setlist.fm can give back events with empty setlists
                if len(sets) > 0:
                    setlist_name = u'{0} at {1}'.format(
                        setlist['artist']['@name'],
                        setlist['@eventDate'])
                    for subset in sets['set']:
                        for song in subset['song']:
                            setlist_tracks += [song['@name']]
                    # We can stop because we have found a setlist
                    break
        except Exception:
            self._log.debug(u'error scraping setlist.fm for {0}'.format(
                            artist_name))

        if not setlist_tracks:
            self._log.info(u'No setlist found')
            return

        # Create a playlist for the found setlist
        self._log.info(u'Setlist: {0} ({1} tracks)'.format(
                        setlist_name, len(setlist_tracks)))
        items = []
        missing_items = []
        for track_nr, track_name in enumerate(setlist_tracks):
            item = _find_item_in_lib(lib, track_name, artist_name)
            if item:
                items += [item]
                message = ui.colorize('text_success', u'found')
            else:
                missing_items += [item]
                message = ui.colorize('text_error', u'not found')
            self._log.info("{0} {1}: {2}".format(
                          (track_nr+1), track_name, message))

        # Create and save the playlist
        m3u_name = setlist_name + '.m3u'
        m3u_path = normpath(os.path.join(
                                self.config['playlist_dir'].as_filename(),
                                m3u_name))
        mkdirall(m3u_path)
        with open(syspath(m3u_path), 'w') as f:
            for item in items:
                f.write(item.path + b'\n')
        self._log.info(u'Saved playlist at "{0}"'.format(m3u_path))

    def commands(self):
        def create(lib, opts, args):
            self.create_playlist(lib, ui.decargs(args))

        setlist_cmd = ui.Subcommand(
            'setlister',
            help='create playlist from an artists\' setlist'
        )

        setlist_cmd.func = create

        return [setlist_cmd]
