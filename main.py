# Copyright (c) 2025 Benoît Pelletier
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import asyncio
import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import datetime
from dismob import log, filehelper, colors

async def setup(bot: commands.Bot):
    log.info("Module `tickets` setup")
    filehelper.ensure_directory("db")
    await bot.add_cog(Tickets(bot))

class Tickets(commands.GroupCog, name="tickets"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_path = "db/tickets.db"
        self.default_panel_title = "Support Tickets"
        self.default_panel_description = "Click a button below to create a support ticket"
        self.default_button_label = "Create Ticket"
        self.default_button_emoji = "🎫"
        self.default_button_color = "primary"
        self.default_ticket_title = "Support Ticket"
        self.default_ticket_message = "Support will be with you shortly."
        self.default_ticket_color = "green"

    # cog load function
    async def cog_load(self):
        await self.setup_db()
        await self.setup_views()

    async def cog_unload(self):
        await self.clear_views()

    async def setup_views(self):
        """Setup persistent views for all configured panels"""
        self.bot.add_view(TicketView(self))
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT guild_id, id FROM ticket_panels")
            panels = await cursor.fetchall()
            
            for guild_id, panel_id in panels:
                view = TicketPanelView(self, guild_id, panel_id)
                await view.load_buttons()
                self.bot.add_view(view)

    async def clear_views(self):
        """Clear all persistent views from the bot"""
        views_to_remove = []
        for view in self.bot.persistent_views:
            if isinstance(view, (TicketPanelView, TicketView)):
                views_to_remove.append(view)
                
        for view in views_to_remove:
            self.bot.persistent_views.remove(view)

    def get_ticket_id(self, ticket_channel_id: int) -> int:
        """Convert a 32-bit integer to a value between 0-1023"""
        return ticket_channel_id & 0x3FF ^ (ticket_channel_id >> 10) & 0x3FF

    async def setup_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    channel_id INTEGER PRIMARY KEY,
                    guild_id INTEGER,
                    user_id INTEGER,
                    created_at TIMESTAMP,
                    closed_at TIMESTAMP,
                    button_id INTEGER
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS ticket_buttons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    panel_id INTEGER,
                    button_label TEXT,
                    ticket_title TEXT,
                    ticket_message TEXT,
                    button_position INTEGER CHECK(button_position BETWEEN 1 AND 3),
                    button_emoji TEXT,
                    button_style TEXT CHECK(button_style IN ('primary', 'secondary', 'success', 'danger', 'link', 'premium')),
                    ticket_color TEXT,
                    FOREIGN KEY(panel_id) REFERENCES ticket_panels(id) ON DELETE CASCADE,
                    UNIQUE(panel_id, button_position)
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ticket_panels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    panel_name TEXT,
                    panel_title TEXT,
                    panel_description TEXT,
                    channel_id INTEGER,
                    message_id INTEGER,
                    category_id INTEGER,
                    log_channel_id INTEGER,
                    UNIQUE(guild_id, panel_name)
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ticket_button_roles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    button_id INTEGER,
                    role_id INTEGER,
                    FOREIGN KEY(button_id) REFERENCES ticket_buttons(id),
                    UNIQUE(button_id, role_id)
                )
            """)
            await db.commit()

    @app_commands.command(name="panel", description="Create or update a ticket panel")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_panel(self,
        interaction: discord.Interaction,
        panel_name: str,
        category: discord.CategoryChannel | None = None,
        log_channel: discord.TextChannel | None = None,
        panel_title: str | None = None,
        panel_description: str | None = None
    ):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT panel_title, panel_description, category_id, log_channel_id FROM ticket_panels WHERE guild_id = ? AND panel_name = ?", (interaction.guild_id, panel_name))
            existing_panel = await cursor.fetchone()

            if all(arg is None for arg in [category, log_channel, panel_title, panel_description]):
                if existing_panel:
                    title, desc, cat_id, log_id = existing_panel
                    await log.client(interaction,
                        f"**Panel Title**: {title or 'Default'}\n"
                        f"**Panel Description**: {desc or 'Default'}\n"
                        f"**Category**: {f'<#{cat_id}>' if cat_id else 'Not Set'}\n"
                        f"**Log Channel**: {f'<#{log_id}>' if log_id else 'Not Set'}",
                        title=f"Ticket Panel '{panel_name}' Configuration")
                else:
                    await log.failure(interaction, f"No configuration found for panel '{panel_name}'. Please provide parameters to set it up.")
                return

            if existing_panel:
                new_panel_title = panel_title if panel_title is not None else existing_panel[0]
                new_panel_description = panel_description if panel_description is not None else existing_panel[1]
                new_category = category.id if category is not None else existing_panel[2]
                new_log_channel = log_channel.id if log_channel is not None else existing_panel[3]
            else:
                new_panel_title = panel_title
                new_panel_description = panel_description
                new_category = category.id if category else None
                new_log_channel = log_channel.id if log_channel else None

            await db.execute("""
                INSERT INTO ticket_panels (guild_id, panel_name, panel_title, panel_description, category_id, log_channel_id)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, panel_name)
                DO UPDATE SET
                    panel_title = excluded.panel_title,
                    panel_description = excluded.panel_description,
                    category_id = excluded.category_id,
                    log_channel_id = excluded.log_channel_id
            """, (interaction.guild_id, panel_name, new_panel_title, new_panel_description, new_category, new_log_channel))
            await db.commit()
        await log.success(interaction, f"Ticket panel '{panel_name}' configured successfully!")

    @app_commands.command(name="delete_panel", description="Delete a ticket panel and all its buttons")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def delete_panel(self,
        interaction: discord.Interaction,
        panel_name: str
    ):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT id FROM ticket_panels WHERE guild_id = ? AND panel_name = ?", (interaction.guild_id, panel_name))
            panel_data = await cursor.fetchone()
            if not panel_data:
                await log.failure(interaction, f"Panel '{panel_name}' not found.")
                return

            await db.execute("DELETE FROM ticket_panels WHERE guild_id = ? AND panel_name = ?", (interaction.guild_id, panel_name))
            await db.commit()
        
        await log.success(interaction, f"Ticket panel '{panel_name}' and all its buttons have been deleted successfully!")

    @app_commands.command(name="button", description="Configure a custom ticket button for a panel")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_button(self,
        interaction: discord.Interaction,
        panel_name: str,
        position: app_commands.Range[int, 1, 3],
        button_label: str | None,
        ticket_title: str | None,
        ticket_message: str | None,
        button_emoji: str | None,
        button_style: discord.ButtonStyle | None,
        ticket_color: str | None,
        support_roles: str | None  # Comma-separated list of role IDs or mentions
    ):
        async with aiosqlite.connect(self.db_path) as db:
            # Check if panel exists
            cursor = await db.execute("SELECT id FROM ticket_panels WHERE guild_id = ? AND panel_name = ?", (interaction.guild_id, panel_name))
            panel_data = await cursor.fetchone()
            if not panel_data:
                await log.failure(interaction, f"Panel '{panel_name}' not found. Please create it first using `/tickets panel`.")
                return
            panel_id = panel_data[0]

            # If all parameters are None, display current button configuration
            if button_label is None and ticket_title is None and ticket_message is None and button_emoji is None and button_style is None and ticket_color is None and support_roles is None:
                cursor = await db.execute("""
                    SELECT b.button_label, b.ticket_title, b.ticket_message, b.button_emoji, b.button_style, b.ticket_color, GROUP_CONCAT(r.role_id)
                    FROM ticket_buttons b
                    LEFT JOIN ticket_button_roles r ON b.id = r.button_id
                    WHERE b.panel_id = ? AND b.button_position = ?
                    GROUP BY b.id
                """, (panel_id, position))
                existing_button = await cursor.fetchone()
                if existing_button:
                    roles_str = ", ".join([f"<@&{r}>" for r in existing_button[6].split(',')]) if existing_button[6] else "None"
                    await log.client(interaction,
                        f"**Button {position} Configuration for Panel '{panel_name}':**\n"
                        f"Label: {existing_button[0]}\n"
                        f"Ticket Title: {existing_button[1]}\n"
                        f"Ticket Message: {existing_button[2]}\n"
                        f"Emoji: {existing_button[3]}\n"
                        f"Style: {existing_button[4]}\n"
                        f"Color: {existing_button[5]}\n"
                        f"Support Roles: {roles_str}",
                        title=f"Ticket Button {position} Configuration")
                else:
                    await log.client(interaction, f"No configuration found for button {position} on panel '{panel_name}'.")
                return

            # Convert ButtonStyle enum to string
            style_name = button_style.name.lower() if button_style else self.default_button_color

            # Update the button configuration
            await db.execute("""
                INSERT INTO ticket_buttons 
                (panel_id, button_label, ticket_title, ticket_message, button_position, button_emoji, button_style, ticket_color)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(panel_id, button_position)
                DO UPDATE SET 
                    button_label = COALESCE(excluded.button_label, button_label),
                    ticket_title = COALESCE(excluded.ticket_title, ticket_title),
                    ticket_message = COALESCE(excluded.ticket_message, ticket_message),
                    button_emoji = COALESCE(excluded.button_emoji, button_emoji),
                    button_style = COALESCE(excluded.button_style, button_style),
                    ticket_color = COALESCE(excluded.ticket_color, ticket_color)
            """, (panel_id, button_label, ticket_title, ticket_message, position, button_emoji, style_name, ticket_color))

            # Update the support roles
            if support_roles is not None:
                # Get the button id
                cursor = await db.execute("""
                    SELECT id FROM ticket_buttons 
                    WHERE panel_id = ? AND button_position = ?
                """, (panel_id, position))
                button_id = (await cursor.fetchone())[0]
                
                # Delete existing roles for this button
                await db.execute("DELETE FROM ticket_button_roles WHERE button_id = ?", (button_id,))
                
                # Parse role mentions or IDs
                role_ids = []
                if support_roles: # Allow empty string to clear roles
                    for role_str in support_roles.split(','):
                        role_str = role_str.strip()
                        if role_str.startswith('<@&') and role_str.endswith('>'):
                            role_id = int(role_str[3:-1])
                        else:
                            try:
                                role_id = int(role_str)
                            except ValueError:
                                continue
                        role_ids.append(role_id)

                # Insert new roles
                for role_id in role_ids:
                    await db.execute("""
                        INSERT INTO ticket_button_roles (button_id, role_id)
                        VALUES (?, ?)
                    """, (button_id, role_id))

            await db.commit()
        
        await log.success(interaction, f"Button {position} for panel '{panel_name}' configured successfully!")

    # Add a command to delete a button at specific position
    @app_commands.command(name="delete_button", description="Delete a custom ticket button from a panel")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def delete_button(self,
        interaction: discord.Interaction,
        panel_name: str,
        position: app_commands.Range[int, 1, 3]
    ):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT b.id FROM ticket_buttons b
                JOIN ticket_panels p ON b.panel_id = p.id
                WHERE p.guild_id = ? AND p.panel_name = ? AND b.button_position = ?
            """, (interaction.guild_id, panel_name, position))
            if not await cursor.fetchone():
                await log.failure(interaction, f"No button found at position {position} on panel '{panel_name}' to delete.")
                return

            await db.execute("""
                DELETE FROM ticket_buttons
                WHERE id IN (
                    SELECT b.id FROM ticket_buttons b
                    JOIN ticket_panels p ON b.panel_id = p.id
                    WHERE p.guild_id = ? AND p.panel_name = ? AND b.button_position = ?
                )
            """, (interaction.guild_id, panel_name, position))
            await db.commit()
        
        await log.success(interaction, f"Button {position} from panel '{panel_name}' deleted successfully!")

    @app_commands.command(name="here", description="Create a ticket panel in the current channel")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_channels=True)
    async def ticket_here(self, interaction: discord.Interaction, panel_name: str, channel: discord.TextChannel | None = None):
        # Get ticket panel settings
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT id, panel_title, panel_description, channel_id, message_id FROM ticket_panels WHERE guild_id = ? AND panel_name = ?",
                (interaction.guild_id, panel_name)
            )
            result = await cursor.fetchone()
            if not result:
                await log.failure(interaction, f"Panel '{panel_name}' not configured! Ask an admin to run `/tickets panel`")
                return
            
            panel_id, panel_title, panel_description, old_channel_id, old_message_id = result

        # Delete previous panel message if exists
        if old_channel_id and old_message_id:
            try:
                channel = interaction.guild.get_channel(old_channel_id)
                if channel:
                    message = await channel.fetch_message(old_message_id)
                    await message.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass  # Message already deleted or no permissions

        view = TicketPanelView(self, interaction.guild_id, panel_id)
        await view.load_buttons()

        new_channel = channel if channel is not None else interaction.channel
        
        embed = discord.Embed(
            title=panel_title or self.default_panel_title,
            description=panel_description or self.default_panel_description,
            color=discord.Color.blurple()
        )
        panel_message = await log.safe_send_message(new_channel, embed=embed, view=view)

        # Store new panel information
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE ticket_panels SET channel_id = ?, message_id = ? WHERE id = ?",
                (new_channel.id, panel_message.id, panel_id)
            )
            await db.commit()
        
        await log.success(interaction, f"Ticket panel '{panel_name}' created successfully!")

    # Command to close manually a ticcket
    @app_commands.command(name="close", description="Close a ticket")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_channels=True)
    async def close_ticket_command(self, interaction: discord.Interaction):
        await self.close_ticket(interaction)

    async def create_ticket(self, interaction: discord.Interaction, title: str, message: str, color: str, button_id: int, panel_id: int, support_roles: list[int] | None = None):
        if not panel_id:
            await log.failure(interaction, "Could not identify the ticket panel. The view may be outdated.")
            return

        async with aiosqlite.connect(self.db_path) as db:
            # Get category_id from the panel
            cursor = await db.execute(
                "SELECT category_id FROM ticket_panels WHERE id = ?", 
                (panel_id,)
            )
            config = await cursor.fetchone()
            
        if not config or not config[0]:
            await log.failure(interaction, "Ticket category not configured for this panel! Ask an admin to run `/tickets panel`")
            return

        category_id = config[0]
        category = interaction.guild.get_channel(category_id)

        # Create channel overwrites
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        if support_roles is not None:
            # Add permissions for each support role
            for role_id in support_roles:
                role = interaction.guild.get_role(role_id)
                if role:
                    overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        # Create ticket channel
        channel = await category.create_text_channel(
            f"ticket-new",
            overwrites=overwrites
        )

        channel = await channel.edit(name=f"ticket-{self.get_ticket_id(channel.id)}")

        # Create private thread for staff
        thread = await channel.create_thread(
            name=f"Staff Discussion",
            type=discord.ChannelType.private_thread,
            invitable=False
        )

        await thread.add_user(interaction.guild.me)
        if support_roles is not None:
            for role_id in support_roles:
                role = interaction.guild.get_role(role_id)
                if role:
                    for member in role.members:
                        try:
                            await thread.add_user(member)
                        except discord.HTTPException:
                            continue

        # Send initial messages
        embed = discord.Embed(
            title=title,
            description=f"Ticket created by {interaction.user.mention}\n{message}",
            color=colors.str_to_color(color),
            timestamp=datetime.datetime.now()
        )
        await log.safe_send_message(channel, embed=embed, view=TicketView(self))

        staff_embed = discord.Embed(
            title="Staff Discussion Thread",
            description=f"Use this private thread to discuss the ticket of {interaction.user.mention}.",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now()
        )
        await thread.send(embed=staff_embed)

        # Save ticket to database
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO tickets (channel_id, guild_id, user_id, created_at, button_id) VALUES (?, ?, ?, ?, ?)",
                (channel.id, interaction.guild_id, interaction.user.id, datetime.datetime.now(), button_id)
            )
            await db.commit()

        await log.success(interaction, f"Ticket created! Check {channel.mention}")

    async def close_ticket(self, interaction: discord.Interaction):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT button_id FROM tickets WHERE channel_id = ?", (interaction.channel_id,))
            ticket_data = await cursor.fetchone()
            if not ticket_data:
                await log.failure(interaction, "This ticket is not registered in the database!")
                return

            button_id = ticket_data[0]

            # Get support roles for this ticket's button
            cursor = await db.execute("SELECT role_id FROM ticket_button_roles WHERE button_id = ?", (button_id,))
            support_roles = [row[0] for row in await cursor.fetchall()]

            if not interaction.user.guild_permissions.administrator:
                # Check if user has any of the support roles
                user_roles = [role.id for role in interaction.user.roles]
                if not any(role_id in user_roles for role_id in support_roles):
                    await log.failure(interaction, "You don't have permission to close this ticket!")
                    return

            # Get log channel from the panel associated with the button
            cursor = await db.execute("""
                SELECT p.log_channel_id FROM ticket_panels p
                JOIN ticket_buttons b ON p.id = b.panel_id
                WHERE b.id = ?
            """, (button_id,))
            result = await cursor.fetchone()
            log_channel_id = result[0] if result else None

            await db.execute(
                "UPDATE tickets SET closed_at = ? WHERE channel_id = ?",
                (datetime.datetime.now(), interaction.channel.id)
            )
            await db.commit()
            
        if log_channel_id:
            log_channel = interaction.guild.get_channel(log_channel_id)
            if log_channel:
                messages = [msg async for msg in interaction.channel.history(limit=None, oldest_first=True)]
                content = "\n".join(f"[{m.created_at}] {m.author}: {m.content}" for m in messages)
                
                now: datetime.datetime = datetime.datetime.now()
                embed = discord.Embed(
                    title=f"Ticket Closed - #{interaction.channel.name}",
                    description=f"Closed by: {interaction.user.mention}",
                    color=discord.Color.red(),
                    timestamp=now
                )

                from io import BytesIO
                file_content = BytesIO(content.encode('utf-8'))
                await log_channel.send(embed=embed, file=discord.File(
                    file_content,
                    filename=f"{now.strftime('%Y%m%d-%H%M%S')}-{interaction.channel.name}.txt"
                ))

        # Archive thread if it exists
        for thread in interaction.channel.threads:
            if thread.name.startswith("Staff Discussion"):
                try:
                    await thread.edit(archived=True, locked=True)
                except discord.HTTPException:
                    pass

        await log.safe_respond(interaction, "Closing ticket in 5 seconds...")
        await asyncio.sleep(5)
        await interaction.channel.delete()

    def get_panel_id_from_interaction(self, interaction: discord.Interaction) -> int | None:
        """Helper to extract panel_id from a button interaction's view."""
        if isinstance(interaction.view, TicketPanelView):
            return interaction.view.panel_id
        return None

    async def get_ticket_button_roles(self, channel_id: int) -> list[int] | None:
        """Get the support roles associated with the ticket's button"""
        async with aiosqlite.connect(self.db_path) as db:
            # First get the ticket info to get button id
            cursor = await db.execute("SELECT button_id FROM tickets WHERE channel_id = ?", (channel_id,))
            result = await cursor.fetchone()
            
            if not result or result[0] is None:
                return [] # Return empty list if no button is associated or ticket not found
                
            button_id = result[0]
            
            # Get support roles for this button
            cursor = await db.execute("""
                SELECT role_id 
                FROM ticket_button_roles 
                WHERE button_id = ?
            """, (button_id,))
            
            return [row[0] for row in await cursor.fetchall()]

# View for a panel containing ticket buttons for members to create new tickets
class TicketPanelView(discord.ui.View):
    def __init__(self, cog, guild_id: int, panel_id: int):
        super().__init__(timeout=None)
        self.cog: Tickets = cog
        self.guild_id = guild_id
        self.panel_id = panel_id
        self.buttons_loaded = False

    async def load_buttons(self):
        if self.buttons_loaded:
            return

        async with aiosqlite.connect(self.cog.db_path) as db:
            cursor = await db.execute(
                """SELECT id, button_label, ticket_title, ticket_message, button_position, 
                   button_emoji, button_style, ticket_color
                   FROM ticket_buttons 
                   WHERE panel_id = ? 
                   ORDER BY button_position""",
                (self.panel_id,)
            )
            buttons = await cursor.fetchall()

            for button_id, label, title, message, position, emoji, style, color in buttons:
                self.add_item(TicketPanelButton(
                    button_id=button_id,
                    label=label,
                    position=position,
                    title=title or self.cog.default_ticket_title,
                    message=message or self.cog.default_ticket_message,
                    guild_id=self.guild_id,
                    emoji=emoji or self.cog.default_button_emoji,
                    style=style or self.cog.default_button_color,
                    ticket_color=color or self.cog.default_ticket_color
                ))

        if not buttons: # If no custom buttons, add default button
            self.add_item(TicketPanelButton(
                button_id=None, # No ID for default button
                label=self.cog.default_button_label,
                position=0,
                title=self.cog.default_ticket_title,
                message=self.cog.default_ticket_message,
                guild_id=self.guild_id,
                emoji=self.cog.default_button_emoji,
                style=self.cog.default_button_color,
                ticket_color=self.cog.default_ticket_color
            ))

        self.buttons_loaded = True

# Button inside the ticket panel
class TicketPanelButton(discord.ui.Button):
    def __init__(self, button_id: int | None, label: str, position: int, title: str, message: str, guild_id: int, emoji: str, style: str, ticket_color: str):
        button_style = getattr(discord.ButtonStyle, style.lower(), discord.ButtonStyle.primary)
        super().__init__(
            label=label,
            style=button_style,
            emoji=emoji,
            custom_id=f"ticket_button_{guild_id}_{position}_{button_id or 'default'}"
        )
        self.button_id = button_id
        self.ticket_title = title
        self.ticket_message = message
        self.ticket_color = ticket_color
        self.position = position

    async def get_support_roles(self) -> list[int]:
        if self.button_id is None:
            return []
        view: TicketPanelView = self.view
        async with aiosqlite.connect(view.cog.db_path) as db:
            # Get support roles for this button
            cursor = await db.execute("""
                SELECT role_id FROM ticket_button_roles WHERE button_id = ?
            """, (self.button_id,))
            return [row[0] for row in await cursor.fetchall()]

    async def callback(self, interaction: discord.Interaction):
        view: TicketPanelView = self.view
        support_roles = await self.get_support_roles()
        await view.cog.create_ticket(interaction, self.ticket_title, self.ticket_message, self.ticket_color, self.button_id, view.panel_id, support_roles)

# View inside a ticket to manage the ticket itself
class TicketView(discord.ui.View):
    def __init__(self, cog: Tickets):
        super().__init__(timeout=None)
        self.cog: Tickets = cog

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="persistent_close_ticket_button")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        tickets_cog = self.cog
        if not tickets_cog:
            await log.failure(interaction, "Ticket system is currently unavailable.")
            return
        await tickets_cog.close_ticket(interaction)
