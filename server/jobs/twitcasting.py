import asyncio
import logging
from datetime import datetime, timezone
from typing import Tuple, Union
from urllib.parse import unquote

import aiohttp

from .utils import VTBiliDatabase

CHROME_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.138 Safari/537.36"  # noqa: E501


async def check_status(
    session: aiohttp.ClientSession, param: dict, channel: str
) -> Tuple[Union[str, None], str]:
    async with session.get(
        "https://twitcasting.tv/streamchecker.php", params=param
    ) as res:
        text_results: Union[str, None] = await res.text()
        if res.status != 200:
            return None, channel
    return text_results, channel


async def get_user_data(
    session: aiohttp.ClientSession, channel: str
) -> Tuple[Union[dict, None], str]:
    uri = "https://frontendapi.twitcasting.tv/users/{}".format(
        channel
    )
    async with session.get(
        uri, params={"detail": True}
    ) as resp:
        json_res: dict = await resp.json()
        if resp.status != 200:
            return None, channel
    return json_res, channel


async def twitcasting_channels(
    DatabaseConn: VTBiliDatabase, twitcast_data: list
):
    vtlog = logging.getLogger("twcast_channels")
    sessions = aiohttp.ClientSession(headers={"User-Agent": CHROME_UA})

    vtlog.info("Collecting IDs...")
    twitcast_id = [twit["id"] for twit in twitcast_data]

    vtlog.info("Creating tasks...")
    twitcast_tasks = [
        get_user_data(sessions, uid) for uid in twitcast_id
    ]

    twitcast_chan_data = []
    vtlog.info("Running all tasks...")
    for twit_task in asyncio.as_completed(twitcast_tasks):
        twit_res, channel = await twit_task
        vtlog.info(f"|-- Checking {channel} data...")
        if not twit_res or "user" not in twit_res:
            vtlog.error(
                f"|--! Failed to fetch info for {channel}, skipping..."
            )
            continue

        udata = twit_res["user"]

        desc = ""
        if udata["description"]:
            desc = udata["description"]

        profile_img = udata["image"]
        if profile_img.startswith("//"):
            profile_img = "https:" + profile_img

        data = {
            "id": channel,
            "name": udata["name"],
            "description": desc,
            "followerCount": udata["backerCount"],
            "level": udata["level"],
            "thumbnail": profile_img,
        }
        twitcast_chan_data.append(data)

    if twitcast_chan_data:
        twitcast_chan_data.sort(key=lambda x: x["id"])

    vtlog.info("Updating database...")
    upd_data = {"twitcasting": twitcast_chan_data}
    await DatabaseConn.update_data("channel_data", upd_data)
    await sessions.close()


async def twitcasting_heartbeat(
    DatabaseConn: VTBiliDatabase, twitcast_data: list
):
    vtlog = logging.getLogger("twcast_heartbeat")
    sessions = aiohttp.ClientSession(headers={"User-Agent": CHROME_UA})

    vtlog.info("Collecting IDs...")
    twitcast_id = [twit["id"] for twit in twitcast_data]

    vtlog.info("Creating tasks...")
    twitcast_tasks = [
        check_status(sessions, {"u": uid, "v": 999}, uid) for uid in twitcast_id
    ]

    tmri = lambda t: int(round(t))  # noqa: E731

    twitcasting_live_data = []
    current_time = datetime.now(tz=timezone.utc).timestamp()
    vtlog.info("Running all tasks...")
    for twit_task in asyncio.as_completed(twitcast_tasks):
        twit_res, channel = await twit_task
        vtlog.info(f"|-- Checking {channel} heartbeat")
        if not twit_res:
            vtlog.error(
                f"|--! Failed to fetch info for {channel}, skipping..."
            )
            continue

        tw_list = twit_res.split("\t")

        tw_sid = tw_list[0]
        if not tw_sid:
            continue
        if tw_sid == "7":
            continue

        tw_time_passed = int(tw_list[6])
        tw_title = unquote(tw_list[7]).strip()

        if tw_title == "":
            tw_title = f"Radio Live #{tw_sid}"

        tw_start_time = tmri(current_time - tw_time_passed)

        dataset = {
            "id": tw_sid,
            "title": tw_title,
            "startTime": tw_start_time,
            "channel": channel,
        }
        twitcasting_live_data.append(dataset)

    if twitcasting_live_data:
        twitcasting_live_data.sort(key=lambda x: x["startTime"])

    vtlog.info("Updating database...")
    upd_data = {"live": twitcasting_live_data}
    await DatabaseConn.update_data("twitcasting_data", upd_data)
    await sessions.close()
