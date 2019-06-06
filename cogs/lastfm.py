import discord
from discord.ext import commands
import helpers.utilityfunctions as util
import os
import requests
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import data.database as db
import arrow
import imgkit
from bs4 import BeautifulSoup


LASTFM_APPID = os.environ['LASTFM_APIKEY']
LASTFM_TOKEN = os.environ['LASTFM_SECRET']


class LastFMError(Exception):
    pass


class LastFm(commands.Cog):

    def __init__(self, client):
        self.client = client
        with open("html/fm_chart_flex.html", "r", encoding="utf-8") as file:
            self.chart_html_flex = file.read().replace('\n', '')

    @commands.group()
    async def fm(self, ctx):
        """Lastfm commands"""
        # await util.command_group_help(ctx)
        ctx.username = db.userdata(ctx.author.id).lastfm_username
        if ctx.invoked_subcommand is not None and ctx.username is None:
            return await ctx.send(f"No saved LastFM username found in database.\n"
                                  f"Use `{self.client.command_prefix}fm set <username>` to set one.")

        await util.command_group_help(ctx)
        # await ctx.send(embed=get_userinfo_embed(ctx.username))

    @fm.command()
    async def set(self, ctx, username):
        """Save your lastfm username"""
        content = get_userinfo_embed(username)
        if content is None:
            await ctx.send(f"Invalid LastFM username `{username}`")

        db.update_user(ctx.author.id, "lastfm_username", username)
        await ctx.send(f"{ctx.message.author.mention} Username saved as `{username}`", embed=content)

    @fm.command()
    async def profile(self, ctx):
        """Lastfm profile"""
        await ctx.send(embed=get_userinfo_embed(ctx.username))

    @fm.command(aliases=['np'])
    async def nowplaying(self, ctx):
        """Currently playing song / most recent song"""
        data = api_request({"user": ctx.username,
                            "method": "user.getrecenttracks",
                            "limit": 1})

        user_attr = data['recenttracks']['@attr']
        tracks = data['recenttracks']['track']
        artist = tracks[0]['artist']['#text']
        album = tracks[0]['album']['#text']
        track = tracks[0]['name']
        image_url = tracks[0]['image'][-1]['#text']
        image_url_small = tracks[0]['image'][1]['#text']
        image_colour = util.color_from_image_url(image_url_small)
        content = discord.Embed()
        content.colour = int(image_colour, 16)
        content.description = f"**{util.escape_md(album)}**"
        content.title = f"**{util.escape_md(artist)}** — ***{util.escape_md(track)} ***"
        content.set_thumbnail(url=image_url)

        # tags and playcount
        trackdata = api_request({"user": ctx.username,
                                 "method": "track.getInfo",
                                 "artist": artist, "track": track},
                                ignore_errors=True)
        if trackdata is not None:
            tags = []
            try:
                trackdata = trackdata['track']
                playcount = int(trackdata['userplaycount'])
                content.description += f"\n`{playcount} play{'s' if playcount > 1 else ''}`"
                for tag in trackdata['toptags']['tag']:
                    tags.append(tag['name'])
                content.set_footer(text=", ".join(tags))
            except KeyError:
                pass

        # play state
        state = "— Most recent track"
        if '@attr' in tracks[0]:
            if "nowplaying" in tracks[0]['@attr']:
                state = "▶ Now Playing"

        content.set_author(name=f"{user_attr['user']} {state}",
                           icon_url=ctx.message.author.avatar_url)

        await ctx.send(embed=content)

    @fm.command(aliases=['ta'])
    async def topartists(self, ctx, *args):
        """Most listened artists"""
        arguments = parse_arguments(args)
        data = api_request({"user": ctx.username,
                            "method": "user.gettopartists",
                            "period": arguments['period'],
                            "limit": arguments['amount']})

        user_attr = data['topartists']['@attr']
        artists = data['topartists']['artist']
        rows = []
        for i, artist in enumerate(artists):
            name = util.escape_md(artist['name'])
            plays = artist['playcount']
            rows.append(f"`{i+1}.` **{plays}** plays — **{name}**")

        image_url = scrape_artist_image(artists[0]['name'])  # artists[0]['image'][-1]['#text']
        image_url_small = artists[0]['image'][1]['#text']
        image_colour = util.color_from_image_url(image_url_small)

        content = discord.Embed()
        content.colour = int(image_colour, 16)
        content.set_thumbnail(url=image_url)
        content.set_footer(text=f"Total unique artists: {user_attr['total']}")
        content.set_author(name=f"{user_attr['user']} — {arguments['amount']} "
                                f"Most played artists {arguments['period']}", icon_url=ctx.message.author.avatar_url)

        await util.send_as_pages(ctx, content, rows, 15)

    @fm.command(aliases=['talb'])
    async def topalbums(self, ctx, *args):
        """Most listened albums"""
        arguments = parse_arguments(args)
        data = api_request({"user": ctx.username,
                            "method": "user.gettopalbums",
                            "period": arguments['period'],
                            "limit": arguments['amount']})

        user_attr = data['topalbums']['@attr']
        albums = data['topalbums']['album']
        rows = []
        for i, album in enumerate(albums):
            name = util.escape_md(album['name'])
            artist_name = util.escape_md(album['artist']['name'])
            plays = album['playcount']
            rows.append(f"`{i + 1}.` **{plays}** plays - **{artist_name}** — ***{name}***")

        image_url = albums[0]['image'][-1]['#text']
        image_url_small = albums[0]['image'][1]['#text']
        image_colour = util.color_from_image_url(image_url_small)

        content = discord.Embed()
        content.colour = int(image_colour, 16)
        content.set_thumbnail(url=image_url)
        content.set_footer(text=f"Total unique albums: {user_attr['total']}")
        content.set_author(name=f"{user_attr['user']} — {arguments['amount']} "
                                f"Most played albums {arguments['period']}", icon_url=ctx.message.author.avatar_url)

        await util.send_as_pages(ctx, content, rows, 15)

    @fm.command(aliases=['tt'])
    async def toptracks(self, ctx, *args):
        """Most listened tracks"""
        arguments = parse_arguments(args)
        data = api_request({"user": ctx.username,
                            "method": "user.gettoptracks",
                            "period": arguments['period'],
                            "limit": arguments['amount']})

        user_attr = data['toptracks']['@attr']
        tracks = data['toptracks']['track']
        rows = []
        for i, track in enumerate(tracks):
            name = util.escape_md(track['name'])
            artist_name = util.escape_md(track['artist']['name'])
            plays = track['playcount']
            rows.append(f"`{i + 1}.` **{plays}** plays - **{artist_name}** — ***{name}***")

        image_url = tracks[0]['image'][-1]['#text']
        image_url_small = tracks[0]['image'][1]['#text']
        image_colour = util.color_from_image_url(image_url_small)

        content = discord.Embed()
        content.colour = int(image_colour, 16)
        content.set_thumbnail(url=image_url)
        content.set_footer(text=f"Total unique tracks: {user_attr['total']}")
        content.set_author(name=f"{user_attr['user']} — {arguments['amount']} "
                                f"Most played tracks {arguments['period']}", icon_url=ctx.message.author.avatar_url)

        await util.send_as_pages(ctx, content, rows, 15)

    @fm.command(aliases=['recents', 're'])
    async def recent(self, ctx, size=15):
        """Recently listened tracks"""
        data = api_request({"user": ctx.username,
                            "method": "user.getrecenttracks",
                            "limit": int(size)})

        user_attr = data['recenttracks']['@attr']
        tracks = data['recenttracks']['track']
        rows = []
        for i, track in enumerate(tracks):
            if i >= size:
                break
            name = util.escape_md(track['name'])
            artist_name = util.escape_md(track['artist']['#text'])
            rows.append(f"**{artist_name}** — ***{name}***")

        image_url = tracks[0]['image'][-1]['#text']
        image_url_small = tracks[0]['image'][1]['#text']
        image_colour = util.color_from_image_url(image_url_small)

        content = discord.Embed()
        content.colour = int(image_colour, 16)
        content.set_thumbnail(url=image_url)
        content.set_footer(text=f"Total scrobbles: {user_attr['total']}")
        content.set_author(name=f"{user_attr['user']} — {size} Recent tracks", icon_url=ctx.message.author.avatar_url)

        await util.send_as_pages(ctx, content, rows, 15)

    @fm.command()
    async def artist(self, ctx, mode, *, artistname):
        """Top tracks / albums for specific artist"""
        await ctx.message.channel.trigger_typing()
        if mode in ["toptracks", "tt", "tracks", "track"]:
            method = "user.gettoptracks"
            path = ["toptracks", "track"]
        elif mode in ["topalbums", "talb", "albums", "album"]:
            method = "user.gettopalbums"
            path = ["topalbums", "album"]
        else:
            return ctx.send_command_help()
            #return await ctx.send(f"ERROR: Invalid mode `{mode}`\ntry `topalbums` or `toptracks`")

        def filter_artist(artist_dict, items):
            for item in items:
                item_artist = item['artist']['name']
                if item_artist.casefold() == artistname.casefold():
                    artist_dict[item['name']] = int(item['playcount'])
            return artist_dict

        data = api_request({"method": method, "user": ctx.username, "limit": 200})
        total_pages = int(data[path[0]]['@attr']['totalPages'])
        artist_data = filter_artist({}, data[path[0]][path[1]])
        if total_pages > 1:
            parameters = [[{"method": method, "user": ctx.username, "limit": 200, "page": i}]
                          for i in range(2, total_pages + 1)]
            gather = await self.client.loop.create_task(threaded(api_request, parameters, len(parameters)))
            for datapacket in gather:
                artist_data = filter_artist(artist_data, datapacket[path[0]][path[1]])

        if not artist_data:
            return await ctx.send(f"You have never listened to **{artistname}**!\nMake sure the artist's name"
                                  f" is formatted exactly as shown in the last fm database.")

        artist_info = api_request({"method": "artist.getinfo", "artist": artistname})['artist']
        image_url = scrape_artist_image(artistname)  # artist_info['image'][-1]['#text']
        image_url_small = scrape_artist_image(artistname)  # artist_info['image'][1]['#text']
        formatted_name = artist_info['name']

        image_colour = util.color_from_image_url(image_url_small)

        content = discord.Embed()
        content.set_thumbnail(url=image_url)
        content.colour = int(image_colour, 16)

        rows = []
        total_plays = 0
        for i, name in enumerate(artist_data):
            line = f"`{i + 1}`. **{artist_data[name]}** plays - **{name}**"
            total_plays += artist_data[name]
            rows.append(line)

        content.set_footer(text=f"Total {total_plays} plays")
        content.title = f"{ctx.username}'s top " \
                        f"{'tracks' if method == 'user.gettoptracks' else 'albums'}" \
                        f" for {formatted_name}"

        await util.send_as_pages(ctx, content, rows)

    @fm.command()
    async def chart(self, ctx, *args):
        """Visual chart of your top albums"""
        await ctx.message.channel.trigger_typing()
        arguments = parse_chart_arguments(args)
        data = api_request({"user": ctx.username,
                            "method": arguments['method'],
                            "period": arguments['period'],
                            "limit": arguments['amount']})

        if arguments['width'] + arguments['height'] > 30:
            return await ctx.send("**ERROR:** Size too big. Chart `width + height` must not exceed `30`")

        chart = []
        chart_type = "ERROR"
        if arguments['method'] == "user.gettopalbums":
            chart_type = "top album"
            albums = data['topalbums']['album']
            for album in albums:
                name = album['name']
                artist = album['artist']['name']
                plays = album['playcount']
                chart.append((f"{plays} plays<br>{name} - {artist}", album['image'][3]['#text']))

        img_divs = ''.join(['<div class="art"><img src="{' + str(i) + '[1]}"><p class="label">{'
                            + str(i) + '[0]}</p></div>' for i in range(len(chart))])
        dimensions = (300*arguments['width'], 300*arguments['height'])
        options = {"xvfb": "", 'quiet': '', 'format': 'jpeg', 'crop-h': dimensions[1], 'crop-w': dimensions[0]}
        formatted_html = self.chart_html_flex.format(width=dimensions[0], height=dimensions[1],
                                                     arts=img_divs).format(*chart)
        imgkit.from_string(formatted_html, "downloads/fmchart.png", options=options,
                           css='html/fm_chart_style.css')
        with open("downloads/fmchart.png", "rb") as img:
            await ctx.send(f"`{ctx.message.author.name} {arguments['period']} {dimensions[0]//300}x{dimensions[1]//300}"
                           f" {chart_type} chart`", file=discord.File(img))

    @commands.command()
    async def whoknows(self, ctx, *, artistname):
        await ctx.message.channel.trigger_typing()
        listeners = []
        tasks = []
        for user in db.query("SELECT user_id, lastfm_username FROM users where lastfm_username is not null"):
            lastfm_username = user[1]

            member = ctx.guild.get_member(user[0])
            if member is None:
                continue

            # is on this server and has lastfm connected
            tasks.append([artistname, lastfm_username, member.name])

        data = await self.client.loop.create_task(threaded(get_playcount, tasks, len(tasks)))
        for playcount, user, name in data:
            if playcount > 0:
                artistname = name
                listeners.append((playcount, user))

        rows = []
        for i, x in enumerate(sorted(listeners, key=lambda p: p[0], reverse=True)):
            if i == 0:
                rank = ":crown:"
            else:
                rank = f"`{i + 1}`."
            rows.append(f"{rank} **{x[1]}** — **{x[0]}** plays")

        content = discord.Embed(title=f"Who knows **{artistname}**?")
        content.set_thumbnail(url=scrape_artist_image(artistname))
        if not rows:
            return await ctx.send(f"Nobody on this server has listened to **{artistname}**")

        await util.send_as_pages(ctx, content, rows)


def setup(client):
    client.add_cog(LastFm(client))


async def threaded(function, datas, workers=20):
    with ThreadPoolExecutor(max_workers=workers) as executor:
        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(
                executor,
                function,
                *data
            )
            for data in datas
        ]
        return await asyncio.gather(*tasks)


def get_playcount(artist, username, reference=None):
    data = api_request({"method": "artist.getinfo", "user": username, "artist": artist})
    try:
        count = int(data['artist']['stats']['userplaycount'])
        name = data['artist']['name']
    except KeyError:
        count = 0
        name = None

    if reference is None:
        return count
    else:
        return count, reference, name


def get_period(timeframe):
    if timeframe in ["7day", "7days", "weekly", "week", "1week"]:
        period = "7day"
    elif timeframe in ["30day", "30days", "monthly", "month", "1month"]:
        period = "1month"
    elif timeframe in ["90day", "90days", "3months", "3month"]:
        period = "3month"
    elif timeframe in ["180day", "180days", "6months", "6month", "halfyear"]:
        period = "6month"
    elif timeframe in ["365day", "365days", "1year", "year", "yr", "12months", "12month", "yearly"]:
        period = "12month"
    elif timeframe in ["at", "alltime", "forever", "overall"]:
        period = "overall"
    else:
        period = None

    return period


def parse_arguments(args):
    parsed = {"period": None, "amount": None}
    for a in args:
        if parsed['amount'] is None:
            try:
                parsed['amount'] = int(a)
                continue
            except ValueError:
                pass
        if parsed['period'] is None:
            parsed['period'] = get_period(a)

    if parsed['period'] is None:
        parsed['period'] = 'overall'
    if parsed['amount'] is None:
        parsed['amount'] = 30
    return parsed


def parse_chart_arguments(args):
    parsed = {"period": None, "amount": None, "width": None, "height": None, "method": None, "path": None}
    for a in args:
        if parsed['amount'] is None:
            try:
                size = a.split('x')
                parsed['width'] = int(size[0])
                if len(size) > 1:
                    parsed['height'] = int(size[1])
                else:
                    parsed['height'] = int(size[0])
                continue
            except ValueError:
                pass

        if parsed['method'] is None:
            if a in ['talb', 'topalbums']:
                parsed['method'] = "user.gettopalbums"
                continue

        if parsed['period'] is None:
            parsed['period'] = get_period(a)

    if parsed['period'] is None:
        parsed['period'] = 'overall'
    if parsed['width'] is None:
        parsed['width'] = 3
        parsed['height'] = 3
    if parsed['method'] is None:
        parsed['method'] = "user.gettopalbums"
    parsed['amount'] = parsed['width'] * parsed['height']
    return parsed


def api_request(url_parameters, ignore_errors=False):
    """Get json data from the lastfm api"""
    url = f"http://ws.audioscrobbler.com/2.0/?api_key={LASTFM_APPID}&format=json"
    for parameter in url_parameters:
        url += f"&{parameter}={url_parameters[parameter]}"
    response = requests.get(url)
    if response.status_code == 200:
        fm_data = json.loads(response.content.decode('utf-8'))
        return fm_data
    else:
        if ignore_errors:
            return None
        else:
            content = json.loads(response.content.decode('utf-8'))
            raise LastFMError(f"Error {content.get('error')} : {content.get('message')}")


def get_userinfo_embed(username):
    data = api_request({"user": username, "method": "user.getinfo"})
    username = data['user']['name']
    playcount = data['user']['playcount']
    profile_url = data['user']['url']
    profile_pic_url = data['user']['image'][3]['#text']
    timestamp = int(data['user']['registered']['unixtime'])
    timestamp = arrow.get(timestamp)

    image_colour = util.color_from_image_url(profile_pic_url)
    content = discord.Embed()
    if image_colour is not None:
        content.colour = int(image_colour, 16)
    else:
        content.colour = discord.Color.magenta()
    content.set_author(name=username)
    content.add_field(name="LastFM profile", value=f"[link]({profile_url})", inline=True)
    content.add_field(name="Registered", value=f"{timestamp.humanize()}\n{timestamp.format('DD/MM/YYYY')}", inline=True)
    content.set_thumbnail(url=profile_pic_url)
    content.set_footer(text=f"Total plays: {playcount}")
    return content


def scrape_artist_image(artist):
    url = f"https://www.last.fm/music/{artist}"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    image = soup.find("meta",  property="og:image")
    return image['content'] if image else None