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
`/tickets panel <panel name> [<category>] [<log channel>] [<title>] [<description>]` | Create or update a panel config for your server. The category is where new tickets will be created. The log channel is where the closed ticket archives are placed.
`/tickets delete_panel <panel_name>` | Delete a panel config and its buttons.
`/tickets button <panel name> <position> [<label>] [<emoji>] [<style>] [<ticket title>] [<ticket message>] [<ticket color>] [<staff roles>] [<user roles>]` | Create or update the button of a panel at a position. Staff roles are the roles that can manage the tickets created by this button. User roles are roles allowed to interact with the button
`/tickets delete_button <panel_name> <position>` | Delete the button config of a panel at position.
`/tickets here <panel name> [<channel>]` | Spawn a ticket panel in this channel (or the specified one if any). Previous panel will be deleted.
`/tickets close` | Manually close the ticket where the command is used.
