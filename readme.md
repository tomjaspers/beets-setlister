# Setlister (WIP)

Plugin for `beets` to generate playlists from the latest setlist for a given artist, using setlist.fm


## Usage
1. Clone this project, or download setlister.py, in to your configured pluginpath (e.g., `~/.beets`)
2. Add `setlister` to your configured beets plugins
3. Configure setlister to know where your playlists have to be placed
```
setlister:
    playlist_dir: ~/Music/setlists
```
4. Run `$ beets setlister artist` to download the artists' latest setlist to your configured playlist directory.