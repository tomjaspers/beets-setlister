# Setlister

Plugin for [beets](https://github.com/sampsyo/beets) to generate playlists from the setlists of a given artist, using [setlist.fm](http://www.setlist.fm)


## Usage
1. Clone this project, or download setlister.py, in to your configured pluginpath (e.g., `~/.beets`)
2. Add `setlister` to your configured beets plugins
3. Configure setlister to know where your playlists have to be placed
```yaml
setlister:
    playlist_dir: ~/Music/setlists
```
Now you can run `$ beets setlister artist` to download the artists' latest setlist to your configured playlist directory, or specify the concert date using the `--date` option.

## Sample
```bash
$ beet setlister alt-j   
Setlist: alt-J at Zenith (17-02-2015) (19 tracks)
1 Hunger of the Pine: found
2 Fitzpleasure: found
3 Something Good: found
4 Left Hand Free: found
5 Dissolve Me: found
6 Matilda: found
7 Bloodflood: found
8 Bloodflood Pt. 2: found
9 Leon: not found
10 ❦ (Ripe & Ruin): found
11 Tessellate: found
12 Every Other Freckle: found
13 Taro: found
14 Warm Foothills: found
15 The Gospel of John Hurt: found
16 Lovely Day: found
17 Nara: found
18 Leaving Nara: found
19 Breezeblocks: found
Saved playlist at "/Users/tjs/Music/setlists/alt-J at Zenith (17-02-2015).m3u"

```