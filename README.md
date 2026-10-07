# team-tpg-scorer

Set `DISCORD_HEADERS` in `bot-public.py` to your Discord authorization header
locally; do not commit credentials. At startup, enter the Discord server ID,
then the channel ID. The script checks that the channel belongs to that server
before selecting auto or historic scoring mode. Both modes fetch messages from
the selected channel and use it in generated Discord links.

Choose `reactions` to enter a Discord message ID and print each reaction's emoji
name followed by the Discord usernames of users who added it. This mode only
reads reactions and does not run scoring.