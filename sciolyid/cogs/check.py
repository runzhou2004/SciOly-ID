# check.py | commands to check answers
# Copyright (C) 2019-2021  EraserBird, person_v1.32, hmmm

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import string
from difflib import get_close_matches

import discord
import discord.ext.commands.view
from discord import app_commands
from discord.ext import commands

from sciolyid.data import (
    database,
    get_aliases,
    format_wiki_url,
    logger,
    possible_words,
    prompts,
)
from sciolyid.data_functions import (
    incorrect_increment,
    item_setup,
    score_increment,
    session_increment,
    streak_increment,
    user_setup,
)
from sciolyid.functions import CustomCooldown
from sciolyid.util import better_spellcheck


class Check(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Check command - argument is the guess
    @commands.hybrid_command(
        help="- Checks your answer.", usage="guess", aliases=["guess", "c"]
    )
    @commands.check(CustomCooldown(3.0, bucket=commands.BucketType.user))
    @app_commands.rename(arg="guess")
    @app_commands.describe(arg="your answer")
    async def check(self, ctx: commands.Context, *, arg: str):
        logger.info("command: check")

        current_item = database.hget(f"channel:{ctx.channel.id}", "item").decode(
            "utf-8"
        )
        if current_item == "":  # no image
            await ctx.send("You must ask for a image first!")
            return

        # if there is a image, it checks answer
        arg = arg.lower()
        current_item = current_item.lower()
        logger.info("current_item: " + current_item)
        logger.info("arg: " + arg)

        item_setup(ctx, current_item)
        correct_list = (x.lower() for x in get_aliases(current_item))

        if database.exists(f"race.data:{ctx.channel.id}"):
            logger.info("race in session")
            if database.hget(f"race.data:{ctx.channel.id}", "strict"):
                logger.info("strict spelling")
                correct = arg in correct_list
            else:
                logger.info("spelling leniency")
                correct = better_spellcheck(arg, correct_list, possible_words)
        else:
            logger.info("no race")
            if database.hget(f"session.data:{ctx.author.id}", "strict"):
                logger.info("strict spelling")
                correct = arg in correct_list
            else:
                logger.info("spelling leniency")
                correct = better_spellcheck(arg, correct_list, possible_words)

        if correct:
            logger.info("correct")

            database.hset(f"channel:{ctx.channel.id}", "item", "")
            database.hset(f"channel:{ctx.channel.id}", "answered", "1")

            session_increment(ctx, "correct", 1)
            streak_increment(ctx, 1)
            database.zincrby(
                f"correct.user:{ctx.author.id}",
                1,
                string.capwords(str(current_item)),
            )

            await ctx.send(
                f"Correct! Good job! The image was **{current_item}**."
                if not database.exists(f"race.data:{ctx.channel.id}")
                else f"**{ctx.author.mention}**, you are correct! The image was **{current_item}**."
            )
            url = format_wiki_url(ctx, current_item)
            await ctx.send(url)  # sends wiki page
            score_increment(ctx, 1)
            if database.exists(f"race.data:{ctx.channel.id}"):

                limit = int(database.hget(f"race.data:{ctx.channel.id}", "limit"))
                first = database.zrevrange(f"race.scores:{ctx.channel.id}", 0, 0, True)[
                    0
                ]
                if int(first[1]) >= limit:
                    logger.info("race ending")
                    race = self.bot.get_cog("Race")
                    await race.stop_race(ctx)
                else:
                    logger.info("auto sending next image")
                    group, state, bw = database.hmget(
                        f"race.data:{ctx.channel.id}", ["group", "state", "bw"]
                    )
                    media = self.bot.get_cog("Media")
                    await media.send_pic(
                        ctx,
                        group.decode("utf-8"),
                        state.decode("utf-8"),
                        bw.decode("utf-8"),
                    )

        elif len(prompts.get(current_item, [])) != 0 and better_spellcheck(
            arg, prompts.get(current_item, []), possible_words
        ):
            logger.info("prompt")
            await ctx.send(
                "Close, but not quite what we were looking for. Can you be more specific?"
            )

        else:
            logger.info("incorrect")

            streak_increment(ctx, None)
            session_increment(ctx, "incorrect", 1)
            incorrect_increment(ctx, str(current_item), 1)

            if database.exists(f"race.data:{ctx.channel.id}"):
                await ctx.send("Sorry, that wasn't the right answer.")
            else:
                database.hset(f"channel:{ctx.channel.id}", "item", "")
                database.hset(f"channel:{ctx.channel.id}", "answered", "1")
                await ctx.send("Sorry, the image was actually " + current_item + ".")
                url = format_wiki_url(ctx, current_item)
                await ctx.send(url)

    async def race_autocheck(self, message: discord.Message):
        if not database.exists(f"race.data:{message.channel.id}"):
            return
        if len(get_close_matches(message.content.strip().lower(), possible_words)) != 0:
            logger.info("race autocheck found: checking")
            ctx = commands.Context(
                message=message,
                bot=self.bot,
                prefix="race-autocheck",
                view=discord.ext.commands.view.StringView(""),
            )
            await user_setup(ctx)
            await self.check(ctx, arg=message.content)


async def setup(bot):
    cog = Check(bot)
    bot.add_message_handler(cog.race_autocheck)
    await bot.add_cog(cog)
