# team-tpg-scorer

`bot-public.py` reads submissions from a Discord channel, calculates the
round's scores, and creates a KMZ map of the results.

## Prerequisites

- Install the Discord app and have the scoring app installed in the server
  containing the submissions. Follow Discord's
  [app installation documentation](https://discord.com/developers/docs/resources/application#installing-apps).
- The app must be able to view the scoring channel and read its message
  history.
- Python 3 and an internet connection (the script uses Discord's API and
  ArcGIS geocoding).
- A `doc.kml` scoring template beside `bot-public.py`. The script reads and
  updates this file; keep a clean backup before each run. This template is not
  included in this repository, so obtain the one used by your team before
  running the scorer.

## Install and configure

1. Download or clone this repository, then open a terminal in its directory.
2. Create and activate a virtual environment:

   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   ```

   On Windows PowerShell, use `py -m venv .venv` and
   `.\.venv\Scripts\Activate.ps1`.
3. Install the Python packages used by the script:

   ```sh
   python -m pip install requests pykml lxml geopy
   ```
4. Edit `DISCORD_HEADERS` near the top of `bot-public.py` and set its
   `Authorization` value to the credential for your installed Discord app,
   using Discord's required authorization format. For example, bot
   credentials use the `Bot ` prefix. Keep credentials private: do not post
   them in chat or commit them to the repository.
5. Place the team's `doc.kml` template in the same directory as
   `bot-public.py`. Optionally place `corrections.json` and `player_list.txt`
   in the working directory (see [Generated and optional files](#generated-and-optional-files)).

## Score a round

Run the script from the repository directory so its files are read and written
there:

```sh
python bot-public.py
```

Follow the prompts:

1. Enter the numeric Discord server ID, then the numeric channel ID. The
   script checks that the channel belongs to that server. Enable Discord
   Developer Mode and use the server/channel context menu's **Copy ID**
   option if you need these IDs.
2. Choose a scoring mode:
   - `auto` looks backward through the selected channel for the configured
     round-start message and scores the messages after it.
   - `historic` asks for the start and end message IDs. The start message is
     excluded and the end message is included. Enable Developer Mode and use
     a message's context menu's **Copy Message ID** option.
3. Wait for the script to finish. It prints submission and distance results.
   Open `Output.kmz` in a compatible map application, such as Google Earth,
   to view the scored round.

Submissions need to match the format expected by the script: a message should
identify the teammate (for example, by mention), provide coordinates or a
location that can be geocoded, and include an image attachment, image embed,
or sticker. The automatic mode's round-start text and recognized usernames
are configured near the top of `bot-public.py`.

## Generated and optional files

- `Output.kmz` contains the result map.
- `messages.json` contains the fetched messages for the selected round.
- `player_map.json` is created or updated to keep Discord users associated
  with consistent display names.
- `corrections.json` is optional; it can provide corrected coordinates for
  player names. Its values should use the coordinate format expected by the
  script.
- `player_list.txt` is optional and is used to report players who are missing
  from the list or did not submit.

Keep these files in the working directory when you want the script to reuse
them on later runs. Do not share files containing credentials.

## Troubleshooting

- **Unable to retrieve channel / 401 or 403 response:** Check the
  authorization value, that the app is installed in the server, and that it
  can view the channel and read message history.
- **Channel does not belong to the selected server:** Copy the IDs again and
  make sure you entered the server and channel IDs from the same server.
- **`FileNotFoundError` for `doc.kml`:** Place the team's KML template beside
  `bot-public.py`; it is not shipped in this repository.
- **`ModuleNotFoundError`:** Activate the virtual environment and install the
  packages listed above.
- **No placemark or a player is listed under “No placemarks”:** Check that
  the message contains the teammate mention, parseable coordinates or location,
  and an image attachment, image embed, or sticker. For historical scoring,
  confirm the start and end IDs and remember the start is excluded.
- **A location cannot be resolved:** Check its spelling and coordinate
  formatting and ensure the machine can reach the internet.
