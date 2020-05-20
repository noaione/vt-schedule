import logging
from datetime import datetime

import aiohttp
import pytz
from motor.motor_asyncio import AsyncIOMotorDatabase

vtlog = logging.getLogger("nijisanji")

NIJI_BILI_UIDS = [
    "434565011",
    "434563934",
    "434563422",
    "436596837",
    "436596839",
    "403921378",
    "477780496",
    "441666968",
    "441666967",
    "511613154",
    "403928672",
    "436596836",
    "403927583",
    "410455162",
    "458154141",
    "434564604",
    "403930401",
    "477780497",
    "458154144",
    "436596840",
    "458154140",
    "458154139",
    "477780499",
    "436596838",
    "458154143",
    "458154142",
    "436596841",
    "477780498",
    "488976342",
    "421267475",
    "420249427",
    "434334701",
    "434341786",
    "434401868",
    "455916618",
    "455965041",
    "472845978",
    "472821519",
    "472877684",
    "477317922",
    "477342747",
    "477306079",
    "480675481",
    "480680646",
    "480745939",
    "474369808",
    "319810877",
    "490331391",
    "56748733",
    "370688671",
    "370689338",
    "370687372",
    "370687588",
    "370689210",
    "392505232",
    "471308347",
    "36795838",
    "98181",
    "1750561",
    "322210278",
    "474113504",
    "282994",
]


async def requests_data(url, params):
    head = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.138 Safari/537.36"  # noqa: E501
    }
    vtlog.debug("\tOpening new session...")
    async with aiohttp.ClientSession(headers=head) as session:
        vtlog.debug("\tRequesting URL...")
        async with session.get(url, params=params) as resp:
            vtlog.debug("\tGetting results...")
            json_results = await resp.json()
    return json_results


async def update_db(db, upcoming_data):
    upd = {"$set": {"upcoming": upcoming_data, "cached": True}}
    upcoming_coll = db["upcoming_niji_data"]
    vtlog.debug("\tSending data...")
    res = await upcoming_coll.update_one({}, upd)
    if res.acknowledged:
        vtlog.info("\tUpdated!")
        return True
    vtlog.error("\tFailed to update...")
    return False


async def fetch_bili_calendar():
    vtlog.debug(f"Total Nijisanji BiliBili IDs: {len(NIJI_BILI_UIDS)}")
    vtubers_uids = ",".join(NIJI_BILI_UIDS)
    current_dt = datetime.now()
    current_ym = current_dt.strftime("%Y-%m")
    current_d = current_dt.day

    vtlog.debug(f"Current date: {current_ym} -- {current_d}")
    api_endpoint = "https://api.live.bilibili.com/xlive/web-ucenter/v2/calendar/GetProgramList"  # noqa: E501
    api_params = {"type": 3, "year_month": current_ym, "ruids": vtubers_uids}

    vtlog.info("Requesting to API...")
    api_responses = await requests_data(api_endpoint, api_params)
    vtlog.info("Parsing results...")
    programs_info = api_responses["data"]["program_infos"]
    users_info = api_responses["data"]["user_infos"]
    date_keys = [int(key) for key in programs_info.keys()]
    date_keys = [date for date in date_keys if date >= current_d]
    vtlog.debug(f"Total date to parse: {len(date_keys)}")

    final_dataset = []
    for date in date_keys:
        for program in programs_info[str(date)]["program_list"]:
            current_utc = datetime.now(tz=pytz.timezone("UTC")).timestamp()
            if current_utc >= program["start_time"]:
                continue
            ch_name = users_info[str(program["ruid"])]["uname"]
            generate_id = (
                f"bili{program['subscription_id']}_{program['program_id']}"
            )
            m_ = {
                "id": generate_id,
                "room_id": program["room_id"],
                "title": program["title"],
                "startTime": program["start_time"],
                "channel": str(program["ruid"]),
                "channel_name": ch_name,
            }
            final_dataset.append(m_)
    vtlog.info("Final sorting and caching...")
    final_dataset.sort(key=lambda x: x["startTime"])
    vtlog.debug(f"Total schedule: {len(final_dataset)}")
    return final_dataset


async def nijisanji_main(DatabaseConn: AsyncIOMotorDatabase):
    vtlog.info("Fetching bili calendar data...")
    calendar_data = await fetch_bili_calendar()

    vtlog.info("Updating database...")
    await update_db(DatabaseConn, calendar_data)
