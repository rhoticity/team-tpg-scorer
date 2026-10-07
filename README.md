# team-tpg-scorer

Set `DISCORD_HEADERS` in `bot-public.py` to your Discord authorization header
locally; do not commit credentials. At startup, enter the Discord server ID,
then the channel or thread ID (including forum posts). The script checks that
the channel or thread belongs to that server (checking a thread's parent when
needed) before selecting auto or historic scoring mode. Both modes fetch messages from
the selected channel and use it in generated Discord links.

Threads use the same Discord API endpoint as channels; enter the thread's own
ID, not its parent channel's ID. The authorized account must be able to view the
parent channel and access the thread, with Read Message History to read messages.
Private threads require membership or Manage Threads permission.
If lookup fails, the script reports the HTTP status when available: 401 means
check `DISCORD_HEADERS`, 403 means check permissions, and 404 means check the
ID and account access. The script cannot bypass Discord access restrictions.

Choose `reactions` to enter a Discord message ID and print each reaction's emoji
name followed by the Discord usernames of users who added it. This mode only
reads reactions and does not run scoring.