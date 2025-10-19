# Dismob Ticket Plugin

This is a [dismob](https://github.com/dismob/dismob) plugin which adds a customizable ticket system.

## Installation

> [!IMPORTANT]
> You need to have an already setup [dismob](https://github.com/dismob/dismob) bot. Follow the instruction there to do it first.

Just download/clone (or add as submodule) this repo into your dismob's `plugins` folder.  
The path **must** be `YourBot/plugins/tickets/main.py` at the end.

Once your bot is up and live, run those commands on your discord server:

```
!modules load tickets
!sync
```

> [!NOTE]
> Replace the prefix `!` by your own bot prefix when doing those commands!

Then you can reload your discord client with `Ctrl+R` to see the new slash commands.

## Commands

Command | Description
--- | ---
`/tickets settings [<category>] [<log channel>] [<title>] [<description>]` | Create or update the panel settings for your server. The category is where new tickets will be created. The log channel is where the closed ticket archives are placed.
`/tickets button <position> [<label>] [<emoji>] [<style>] [<ticket title>] [<ticket message>] [<ticket color>] [<roles>]` | Create or update the button of the panel at a position. Roles are the roles that manage the tickets created by this button.
`/tickets delete_button <position>` | Delete the button config at position.
`/tickets here` | Spawn the ticket panel in this channel. Previous panel will be deleted.
`/tickets close` | Manually close the ticket where the command is used.
