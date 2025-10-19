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
        """Setup persistent views for all configured guilds"""
        self.bot.add_view(TicketView(self))
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT DISTINCT guild_id FROM ticket_config")
            guild_ids = await cursor.fetchall()
            
            for (guild_id,) in guild_ids:
                view = TicketPanelView(self, guild_id)
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
                CREATE TABLE IF NOT EXISTS ticket_config (
                    guild_id INTEGER PRIMARY KEY,
                    category_id INTEGER,
                    log_channel_id INTEGER,
                    panel_title TEXT,
                    panel_description TEXT
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    channel_id INTEGER PRIMARY KEY,
                    guild_id INTEGER,
                    user_id INTEGER,
                    created_at TIMESTAMP,
                    closed_at TIMESTAMP
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS ticket_buttons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    button_label TEXT,
                    ticket_title TEXT,
                    ticket_message TEXT,
                    button_position INTEGER CHECK(button_position BETWEEN 1 AND 3),
                    button_emoji TEXT,
                    button_style TEXT CHECK(button_style IN ('primary', 'secondary', 'success', 'danger', 'link', 'premium')),
                    ticket_color TEXT,
                    FOREIGN KEY(guild_id) REFERENCES ticket_config(guild_id),
                    UNIQUE(guild_id, button_position)
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ticket_panels (
                    guild_id INTEGER,
                    channel_id INTEGER,
                    message_id INTEGER,
                    PRIMARY KEY (guild_id, channel_id, message_id),
                    FOREIGN KEY(guild_id) REFERENCES ticket_config(guild_id)
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

    @app_commands.command(name="settings", description="Setup the ticket system")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_tickets(self, 
        interaction: discord.Interaction, 
        category: discord.CategoryChannel = None,
        log_channel: discord.TextChannel = None,
        panel_title: str = None,
        panel_description: str = None
    ):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT category_id, log_channel_id, panel_title, panel_description FROM ticket_config WHERE guild_id = ?", (interaction.guild_id,))
            existing_config = await cursor.fetchone()
            if existing_config:
                old_category_id, old_log_channel_id, old_panel_title, old_panel_description = existing_config
            else:
                old_category_id = old_log_channel_id = old_panel_title = old_panel_description = None

            if not category and not log_channel and not panel_title and not panel_description:
                if existing_config:
                    await log.client(interaction,
                        f"{f'Category: {f'<#{old_category_id}>' if old_category_id is not None else 'No category set'}'}\n"
                        f"{f'Log Channel: {f'<#{old_log_channel_id}>' if old_log_channel_id is not None else 'No log channel set'}'}\n"
                        f"Panel Title: {old_panel_title if old_panel_title is not None else "Default"}\n"
                        f"Panel Description: {old_panel_description if old_panel_description is not None else "Default"}",
                        title="Ticket System Configuration")
                else:
                    await log.client(interaction, "No configuration found. Please provide parameters to set up.")
                
            new_category = category.id if category is not None else old_category_id
            new_log_channel = log_channel.id if log_channel is not None else old_log_channel_id
            new_panel_title = panel_title if panel_title is not None else old_panel_title
            new_panel_description = panel_description if panel_description is not None else old_panel_description
            
            await db.execute("""
                INSERT INTO ticket_config 
                (guild_id, category_id, log_channel_id, panel_title, panel_description) 
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(guild_id)
                DO UPDATE SET 
                    category_id = excluded.category_id, 
                    log_channel_id = excluded.log_channel_id, 
                    panel_title = excluded.panel_title,
                    panel_description = excluded.panel_description
            """, (interaction.guild_id, new_category, new_log_channel, new_panel_title, new_panel_description))
            await db.commit()
        await log.success(interaction, "Ticket system configured successfully!")

    @app_commands.command(name="button", description="Configure a custom ticket button")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_button(self,
        interaction: discord.Interaction,
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
            # Check if ticket system is configured
            cursor = await db.execute("SELECT 1 FROM ticket_config WHERE guild_id = ?", (interaction.guild_id,))
            if not await cursor.fetchone():
                await log.failure(interaction, "Please configure the ticket system first using /tickets settings")
                return

            # If all parameters are None, display current button configuration
            if button_label is None and ticket_title is None and ticket_message is None and button_emoji is None and button_style is None:
                cursor = await db.execute("""
                    SELECT button_label, ticket_title, ticket_message, button_emoji, button_style 
                    FROM ticket_buttons 
                    WHERE guild_id = ? AND button_position = ?
                """, (interaction.guild_id, position))
                existing_button = await cursor.fetchone()
                if existing_button:
                    await log.client(interaction,
                        f"**Button {position} Configuration:**\n"
                        f"Label: {existing_button[0]}\n"
                        f"Ticket Title: {existing_button[1]}\n"
                        f"Ticket Message: {existing_button[2]}\n"
                        f"Emoji: {existing_button[3]}\n"
                        f"Style: {existing_button[4]}",
                        title=f"Ticket Button {position} Configuration")
                else:
                    await log.client(interaction, f"No configuration found for button {position}. Please provide parameters to set it up.")
                return

            # Convert ButtonStyle enum to string
            style_name = button_style.name.lower() if button_style else self.default_button_color

            # Update the button configuration
            await db.execute("""
                INSERT INTO ticket_buttons 
                (guild_id, button_label, ticket_title, ticket_message, button_position, button_emoji, button_style, ticket_color)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, button_position)
                DO UPDATE SET 
                    button_label = excluded.button_label,
                    ticket_title = excluded.ticket_title,
                    ticket_message = excluded.ticket_message,
                    button_emoji = excluded.button_emoji,
                    button_style = excluded.button_style,
                    ticket_color = excluded.ticket_color
            """, (interaction.guild_id, button_label, ticket_title, ticket_message, position, button_emoji, style_name, ticket_color))

            # Update the support roles
            if support_roles:
                # Get the button id
                cursor = await db.execute("""
                    SELECT id FROM ticket_buttons 
                    WHERE guild_id = ? AND button_position = ?
                """, (interaction.guild_id, position))
                button_id = (await cursor.fetchone())[0]
                
                # Delete existing roles for this button
                await db.execute("DELETE FROM ticket_button_roles WHERE button_id = ?", (button_id,))
                
                # Parse role mentions or IDs
                role_ids = []
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
        
        await log.success(interaction, f"Button {position} configured successfully!")

    # Add a command to delete a button at specific position
    @app_commands.command(name="delete_button", description="Delete a custom ticket button")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def delete_button(self,
        interaction: discord.Interaction,
        position: app_commands.Range[int, 1, 3]
    ):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT 1 FROM ticket_buttons 
                WHERE guild_id = ? AND button_position = ?
            """, (interaction.guild_id, position))
            if not await cursor.fetchone():
                await log.failure(interaction, f"No button found at position {position} to delete.")
                return

            await db.execute("""
                DELETE FROM ticket_buttons 
                WHERE guild_id = ? AND button_position = ?
            """, (interaction.guild_id, position))
            await db.commit()
        
        await log.success(interaction, f"Button {position} deleted successfully!")

    @app_commands.command(name="here", description="Create the ticket buttons in the current channel")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_channels=True)
    async def ticket_here(self, interaction: discord.Interaction):
        # Get ticket panel settings
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT panel_title, panel_description FROM ticket_config WHERE guild_id = ?",
                (interaction.guild_id,)
            )
            result = await cursor.fetchone()
            if not result:
                await log.failure(interaction, "Ticket system not configured! Ask an admin to run /tickets settings")
                return
            
            panel_title, panel_description = result

        # Delete previous panel if exists
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT channel_id, message_id FROM ticket_panels WHERE guild_id = ?",
                (interaction.guild_id,)
            )
            panels = await cursor.fetchall()
            
            for channel_id, message_id in panels:
                try:
                    channel = interaction.guild.get_channel(channel_id)
                    if channel:
                        message = await channel.fetch_message(message_id)
                        await message.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass  # Message already deleted or no permissions
                
            # Clear old panels from database
            await db.execute(
                "DELETE FROM ticket_panels WHERE guild_id = ?",
                (interaction.guild_id,)
            )
            await db.commit()

        view = TicketPanelView(self, interaction.guild_id)
        await view.load_buttons()
        
        embed = discord.Embed(
            title=panel_title or self.default_panel_title,
            description=panel_description or self.default_panel_description,
            color=discord.Color.blurple()
        )
        panel_message = await log.safe_send_message(interaction.channel, embed=embed, view=view)

        # Store new panel information
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO ticket_panels (guild_id, channel_id, message_id) VALUES (?, ?, ?)",
                (interaction.guild_id, interaction.channel_id, panel_message.id)
            )
            await db.commit()
        
        await log.success(interaction, "Ticket panel created successfully!")

    # Command to close manually a ticcket
    @app_commands.command(name="close", description="Close a ticket")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_channels=True)
    async def close_ticket_command(self, interaction: discord.Interaction):
        await self.close_ticket(interaction)

    async def create_ticket(self, interaction: discord.Interaction, title: str, message: str, color: str, support_roles: list[int] | None = None):
        async with aiosqlite.connect(self.db_path) as db:
            # Get category_id from config
            cursor = await db.execute(
                "SELECT category_id FROM ticket_config WHERE guild_id = ?", 
                (interaction.guild_id,)
            )
            config = await cursor.fetchone()
            
        if not config:
            await log.failure(interaction, "Ticket system not configured! Ask an admin to run /ticket settings")
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
                "INSERT INTO tickets (channel_id, guild_id, user_id, created_at) VALUES (?, ?, ?, ?)",
                (channel.id, interaction.guild_id, interaction.user.id, datetime.datetime.now())
            )
            await db.commit()

        await log.success(interaction, f"Ticket created! Check {channel.mention}")

    async def close_ticket(self, interaction: discord.Interaction):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM tickets WHERE channel_id = ?", (interaction.channel_id,))
            count_result = await cursor.fetchone()
            if count_result[0] == 0:
                await log.failure(interaction, "This ticket is not registered in the database!")
                return

            # Get support roles for this ticket's button
            support_roles = await self.get_ticket_button_roles(interaction.channel_id)
            if support_roles is None:
                await log.failure(interaction, "Could not find ticket configuration!")
                return

            if not interaction.user.guild_permissions.administrator:
                # Check if user has any of the support roles
                user_roles = [role.id for role in interaction.user.roles]
                if not any(role_id in user_roles for role_id in support_roles):
                    await log.failure(interaction, "You don't have permission to close this ticket!")
                    return

            # Get log channel
            cursor = await db.execute(
                "SELECT log_channel_id FROM ticket_config WHERE guild_id = ?",
                (interaction.guild_id,)
            )
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
                    filename=f"{now.strftime("%Y%m%d-%H%M%S")}-{interaction.channel.name}.txt"
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

    async def get_ticket_button_roles(self, channel_id: int) -> list[int] | None:
        """Get the support roles associated with the ticket's button"""
        async with aiosqlite.connect(self.db_path) as db:
            # First get the ticket info to get button position
            cursor = await db.execute("""
                SELECT t.channel_id, tb.id
                FROM tickets t
                JOIN ticket_buttons tb ON tb.guild_id = t.guild_id
                WHERE t.channel_id = ?
            """, (channel_id,))
            result = await cursor.fetchone()
            
            if not result:
                return None
                
            button_id = result[1]
            
            # Get support roles for this button
            cursor = await db.execute("""
                SELECT role_id 
                FROM ticket_button_roles 
                WHERE button_id = ?
            """, (button_id,))
            
            return [row[0] for row in await cursor.fetchall()]

# View for a panel containing ticket buttons for members to create new tickets
class TicketPanelView(discord.ui.View):
    def __init__(self, cog, guild_id: int):
        super().__init__(timeout=None)
        self.cog: Tickets = cog
        self.guild_id = guild_id
        self.buttons_loaded = False

    async def load_buttons(self):
        if self.buttons_loaded:
            return

        async with aiosqlite.connect(self.cog.db_path) as db:
            cursor = await db.execute(
                """SELECT button_label, ticket_title, ticket_message, button_position, 
                   button_emoji, button_style, ticket_color
                   FROM ticket_buttons 
                   WHERE guild_id = ? 
                   ORDER BY button_position""",
                (self.guild_id,)
            )
            buttons = await cursor.fetchall()

            for label, title, message, position, emoji, style, color in buttons:
                self.add_item(TicketPanelButton(
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
    def __init__(self, label: str, position: int, title: str, message: str, guild_id: int, emoji: str, style: str, ticket_color: str):
        button_style = getattr(discord.ButtonStyle, style.upper(), discord.ButtonStyle.primary)
        super().__init__(
            label=label,
            style=button_style,
            emoji=emoji,
            custom_id=f"ticket_button_{guild_id}_{position}"
        )
        self.ticket_title = title
        self.ticket_message = message
        self.ticket_color = ticket_color
        self.position = position

    async def get_support_roles(self, guild_id: int) -> list[int] | None:
        view: TicketPanelView = self.view
        async with aiosqlite.connect(view.cog.db_path) as db:
            cursor = await db.execute("""
                SELECT id 
                FROM ticket_buttons
                WHERE guild_id = ? AND button_position = ?
            """, (guild_id, self.position))
            button_data = await cursor.fetchone()
            
            # No configuration found
            if not button_data:
                return None

            button_id = button_data[0]
            
            # Get support roles for this button
            cursor = await db.execute("""
                SELECT role_id FROM ticket_button_roles WHERE button_id = ?
            """, (button_id,))
            return [row[0] for row in await cursor.fetchall()]

    async def callback(self, interaction: discord.Interaction):
        view: TicketPanelView = self.view
        support_roles = await self.get_support_roles(interaction.guild_id)
        await view.cog.create_ticket(interaction, self.ticket_title, self.ticket_message, self.ticket_color, support_roles)

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
