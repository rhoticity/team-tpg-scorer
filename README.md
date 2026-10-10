# team-tpg-scorer

Set the `DISCORD_TOKEN` environment variable to your Discord bot token locally;
do not commit credentials. At startup, enter the Discord server ID,
then the channel or thread ID (including forum posts). The script checks that
the channel or thread belongs to that server (checking a thread's parent when
needed) before selecting auto or historic scoring mode. Both modes fetch messages from
the selected channel and use it in generated Discord links.

Threads use the same Discord API endpoint as channels; enter the thread's own
ID, not its parent channel's ID. The authorized account must be able to view the
parent channel and access the thread, with Read Message History to read messages.
Private threads require membership or Manage Threads permission.
If lookup fails, the script reports the HTTP status when available: 401 means
check `DISCORD_TOKEN`, 403 means check permissions, and 404 means check the
ID and account access. The script cannot bypass Discord access restrictions.

### Troubleshooting a public thread returning HTTP 403

- The script uses the **bot** identity printed by the authentication test, not
  your personal Discord account. HTTP 200 from authentication only validates the
  token; your own ability to open a thread does not establish the bot's access.
- Confirm that this bot is installed as a server member in the selected server.
  In Discord, enable Developer Mode and copy the thread/post ID and its containing
  channel's ID. A forum post's parent is the forum channel.
- Ask a server administrator to check **View Channel** for the bot in the parent
  channel, including `@everyone`, bot roles, and member-specific permission
  overrides. Also grant **Read Message History** for scoring. Public threads
  do not require private-thread membership; do not make the bot an administrator
  just to troubleshoot.
- On a 403, the script reports Discord's numeric error code when available:
  `50001` is Missing Access and `50013` is Missing Permissions. It offers an
  optional parent-channel lookup using the same bot token (Enter skips it).
  A failed parent lookup points to the parent ID, server membership, or channel
  access. A successful lookup only establishes parent metadata access: confirm
  it is the actual parent and recheck the thread ID and thread type. The script
  still requires a successful lookup of the target thread before proceeding.
- If you need more help, share the HTTP status, numeric error code, whether the
  parent lookup succeeds, and the thread type with the server administrator.
  Never share your bot token or Authorization header.

Choose `reactions` to enter a Discord message ID and print each reaction's emoji
name followed by the Discord usernames of users who added it. This mode only
reads reactions and does not run scoring.