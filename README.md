# team-tpg-scorer

Set `DISCORD_HEADERS` in `bot-public.py` to your Discord authorization header
locally; do not commit credentials. At startup, enter the Discord server ID,
then the channel ID. The script checks that the channel belongs to that server
before selecting auto or historic scoring mode. Both modes fetch messages from
the selected channel and use it in generated Discord links.