import discord
from discord.ext import commands
import discord.utils as discordutils
import requests
import json
import math
import psutil
import time
import os
import arrow
import copy
import helpers.utilityfunctions as util
import data.database as db
from operator import itemgetter


class Info(commands.Cog):

    def __init__(self, client):
        self.client = client
        self.start_time = time.time()
        self.version = str(get_version())

    @commands.command()
    async def invite(self, ctx):
        """Invite miso to your server!"""
        url = discordutils.oauth_url('500385855072894982', permissions=discord.Permissions(269347911))
        await ctx.send(f">>> Use this link to invite me to your server!\n"
                       f"The selected permissions are **required** for everything to function properly, make sure not to disable any!\n<{url}>")

    @commands.command()
    async def patreon(self, ctx):
        """Link to the patreon page"""
        await ctx.send("https://www.patreon.com/joinemm")

    @commands.command()
    async def patrons(self, ctx):
        """List the current patreons"""
        patrons = db.query("select user_id, currently_active from patrons")
        content = discord.Embed(title="Patreon supporters ❤", color=discord.Color.red())
        current = []
        past = []
        for x in patrons:
            user = self.client.get_user(x[0])
            if util.int_to_bool(x[1]):
                current.append(user or x[0])
            else:
                past.append(user or x[0])

        if current:
            content.add_field(name="Current patrons", value="\n".join([f"**{x}**" for x in current]))
        if past:
            content.add_field(name="Inactive patrons", value="\n".join([f"**{x}**" for x in past]))

        await ctx.send(embed=content)

    @commands.command(name='info')
    async def info(self, ctx):
        """Get information about the bot"""
        membercount = len(set(self.client.get_all_members()))
        content = discord.Embed(title=f"Miso Bot | version {self.version}", colour=discord.Colour.red())
        content.description = f"""
Created by **{self.client.appinfo.owner}** {self.client.appinfo.owner.mention}

Use `{self.client.command_prefix}help` to get the full list of commands, 
or visit the documention website for more detailed help.

Currently active in **{len(self.client.guilds)}** servers,
totaling **{membercount}** unique users.
"""

        content.set_thumbnail(url=self.client.user.avatar_url)
        content.add_field(name='Github', value='https://github.com/joinemm/misobot2', inline=False)
        content.add_field(name='Documentation', value="https://misobot.xyz", inline=False)
        content.add_field(name='Patreon', value="https://www.patreon.com/joinemm", inline=False)

        data = get_commits("joinemm", "misobot2")
        last_update = data[0]['commit']['author'].get('date')
        content.set_footer(text=f"Latest update: {arrow.get(last_update).humanize()}")

        await ctx.send(embed=content)

    @commands.command()
    async def ping(self, ctx):
        """Get the bot's ping"""
        pong_msg = await ctx.send(":ping_pong:")
        sr_lat = (pong_msg.created_at - ctx.message.created_at).total_seconds() * 1000
        await pong_msg.edit(content=f"Command latency = `{sr_lat}`ms\n"
                                    f"Discord latency = `{self.client.latency * 1000:.1f}`ms")

    @commands.command(aliases=['uptime'])
    async def status(self, ctx):
        """Get the bot's status"""
        up_time = time.time() - self.start_time
        uptime_string = util.stringfromtime(up_time, 2)
        stime = time.time() - psutil.boot_time()
        system_uptime_string = util.stringfromtime(stime, 2)

        mem = psutil.virtual_memory()
        pid = os.getpid()
        memory_use = psutil.Process(pid).memory_info()[0]

        content = discord.Embed(title=f"Miso Bot | version {self.version}")
        content.set_thumbnail(url=self.client.user.avatar_url)

        content.add_field(name="Bot process uptime", value=uptime_string)
        content.add_field(name="System CPU Usage", value=f"{psutil.cpu_percent()}%")
        content.add_field(name="System uptime", value=system_uptime_string)
        content.add_field(name="System RAM Usage", value=f"{mem.percent}%")
        content.add_field(name="Bot memory usage", value=f"{memory_use / math.pow(1024, 2):.2f}MB")
        content.add_field(name="Discord API latency", value=f"{self.client.latency * 1000:.1f}ms")

        await ctx.send(embed=content)

    @commands.command()
    async def changelog(self, ctx):
        """Github commit history"""
        author = "joinemm"
        repo = "misobot2"
        data = get_commits(author, repo)
        content = discord.Embed(color=discord.Color.from_rgb(46, 188, 79))
        content.set_author(name="Github commit history", icon_url=data[0]['author']['avatar_url'],
                           url=f"https://github.com/{author}/{repo}/commits/master")
        content.set_thumbnail(url='http://www.logospng.com/images/182/github-icon-182553.png')

        pages = []
        i = 0
        for commit in data:
            if i == 5:
                pages.append(content)
                content = copy.deepcopy(content)
                content.clear_fields()
                i = 0
            sha = commit['sha'][:7]
            author = commit['author'].get('login') if commit['author'] else 'UNKNOWN'
            date = commit['commit']['author'].get('date')
            arrow_date = arrow.get(date)
            url = commit['html_url']
            content.add_field(name=f"[`{sha}`] {commit['commit'].get('message')}",
                              value=f"**{author}** committed {arrow_date.humanize()} | [link]({url})",
                              inline=False)
            i += 1
        pages.append(content)
        await util.page_switcher(ctx, pages)

    @commands.command()
    async def commandstats(self, ctx, *args):
        content = discord.Embed(color=discord.Color.teal())
        globaldata = 'global' in args
        mydata = 'my' in args

        content.title = f"`>_` Most used commands" \
                        + ("" if globaldata else f" in {ctx.guild}") \
                        + (f" by {ctx.author}" if mydata else "")

        if globaldata:
            if mydata:
                data = db.query("SELECT command, SUM(count) FROM command_usage WHERE user_id = ?"
                                "GROUP BY command", (ctx.author.id,))
            else:
                data = db.query("SELECT command, SUM(count) FROM command_usage "
                                "GROUP BY command")
        else:
            if mydata:
                data = db.query("SELECT command, SUM(count) FROM command_usage WHERE guild_id = ? AND user_id = ?"
                                "GROUP BY command",
                                (ctx.guild.id, ctx.author.id))
            else:
                data = db.query("SELECT command, SUM(count) FROM command_usage WHERE guild_id = ? "
                                "GROUP BY command",
                                (ctx.guild.id,))

        rows = []
        total = 0
        for command, count in sorted(data, key=itemgetter(1), reverse=True):
            total += count
            user = None
            biggest_user = (None, None)
            if not mydata:
                if globaldata:
                    biggest_user = db.query("SELECT user_id, MAX(count) AS highest FROM command_usage "
                                            "WHERE command = ?", (command,))[0]
                else:
                    biggest_user = db.query("SELECT user_id, MAX(count) AS highest FROM command_usage "
                                            "WHERE command = ? AND guild_id = ?", (command, ctx.guild.id))[0]
                user = self.client.get_user(biggest_user[0])

            rows.append(f"**x{count} {command}**"
                        + (f" - most uses by `{user}` (**{biggest_user[1]}**)" if not mydata else ""))

        content.set_footer(text=f"Total {total} commands used since 11/08/2019")

        await util.send_as_pages(ctx, content, rows)


def setup(client):
    client.add_cog(Info(client))

def get_version():
    data = requests.get("https://api.github.com/repos/joinemm/misobot2/contributors").json()
    return (data[0].get('contributions')+1) * 0.01

def get_commits(author, repository):
    url = f"https://api.github.com/repos/{author}/{repository}/commits"
    response = requests.get(url)
    data = json.loads(response.content.decode('utf-8'))
    return data
