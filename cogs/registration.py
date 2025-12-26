import discord
from discord.ext import commands
from discord import app_commands, ui
from typing import Optional
import logging

logger = logging.getLogger(__name__)

import database


# User-specific timezone UI removed


class RegisterView(ui.View):
    """Confirmation view for registration."""
    
    def __init__(self, user_id: str, username: str, action: str):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.username = username
        self.action = action
    
    @ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm_button(self, interaction: discord.Interaction, button: ui.Button):
        if self.action == "register":
            success = database.register_user(self.user_id, self.username)
            if success:
                await interaction.response.edit_message(
                    content=(
                        "✅ **You're registered for daily standups!**\n\n"
                        "You'll receive a DM at the start of each collection window.\n"
                        "Use `/my_status` to check your status.\n"
                        "Use `/unregister` if you want to opt out."
                    ),
                    view=None
                )
            else:
                await interaction.response.edit_message(
                    content="ℹ️ You're already registered for standups!",
                    view=None
                )
        elif self.action == "unregister":
            success = database.unregister_user(self.user_id)
            if success:
                await interaction.response.edit_message(
                    content=(
                        "✅ **You've been unregistered from standups.**\n\n"
                        "You won't receive standup DMs anymore.\n"
                        "Use `/register` if you want to opt back in."
                    ),
                    view=None
                )
            else:
                await interaction.response.edit_message(
                    content="ℹ️ You're not currently registered for standups.",
                    view=None
                )
    
    @ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(
            content="❌ Action cancelled.",
            view=None
        )


class RegistrationCog(commands.Cog):
    """Handles user registration for standups (opt-in/opt-out)."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(name="register", description="Register for daily standups")
    async def register(self, interaction: discord.Interaction):
        """Register for daily standups."""
        user_id = str(interaction.user.id)
        username = interaction.user.name
        
        # Check if already registered
        if database.is_user_registered(user_id):
            await interaction.response.send_message(
                "ℹ️ You're already registered for standups!\n"
                "Use `/my_status` to check your status.",
                ephemeral=True
            )
            return
        
        await interaction.response.send_message(
            "📋 **Register for Daily Standups**\n\n"
            "By registering, you'll receive a DM at the start of each standup window.\n"
            "You can answer the questions at your own pace.\n\n"
            "Click **Confirm** to register:",
            view=RegisterView(user_id, username, "register"),
            ephemeral=True
        )
    
    @app_commands.command(name="unregister", description="Opt out of daily standups")
    async def unregister(self, interaction: discord.Interaction):
        """Unregister from daily standups."""
        user_id = str(interaction.user.id)
        username = interaction.user.name
        
        # Check if registered
        if not database.is_user_registered(user_id):
            await interaction.response.send_message(
                "ℹ️ You're not currently registered for standups.\n"
                "Use `/register` to opt in.",
                ephemeral=True
            )
            return
        
        await interaction.response.send_message(
            "⚠️ **Unregister from Standups**\n\n"
            "You'll stop receiving standup DMs.\n"
            "You can re-register anytime with `/register`.\n\n"
            "Click **Confirm** to unregister:",
            view=RegisterView(user_id, username, "unregister"),
            ephemeral=True
        )
    
    @app_commands.command(name="my_status", description="Check your standup registration and response status")
    async def my_status(self, interaction: discord.Interaction):
        """Show user's registration and response status."""
        user_id = str(interaction.user.id)
        
        is_registered = database.is_user_registered(user_id)
        settings = database.get_settings()
        
        if not is_registered:
            await interaction.response.send_message(
                "📋 **Your Standup Status**\n\n"
                "❌ **Not Registered**\n"
                "Use `/register` to opt in to daily standups.",
                ephemeral=True
            )
            return
        
        # Get today's response
        response = database.get_user_response(user_id)
        
        status_lines = [
            "📋 **Your Standup Status**\n",
            "✅ **Registered** for daily standups\n"
        ]
        
        if response:
            status_lines.append(f"✅ **Responded** for {response['standup_date']}")
            if response['edited_at']:
                status_lines.append(f"   _(edited at {response['edited_at']})_")
            if response['is_late']:
                status_lines.append("   ⚠️ _Late submission_")
        else:
            standup_date = database.get_standup_date()
            status_lines.append(f"❌ **Not yet responded** for {standup_date}")
            if database.is_within_collection_window():
                status_lines.append("   📝 _Collection window is open!_")
        
        status_lines.append(f"\n🌍 Team Timezone: `{settings['timezone']}`")
        status_lines.append(f"⏰ Collection Window: `{settings['start_time']}` - `{settings['end_time']}`")
        
        await interaction.response.send_message(
            "\n".join(status_lines),
            ephemeral=True
        )
    
    @app_commands.command(name="no_update", description="Mark that you have no update today")
    async def no_update(self, interaction: discord.Interaction):
        """Explicitly mark that you have no update today."""
        user_id = str(interaction.user.id)
        username = interaction.user.name
        
        if not database.is_user_registered(user_id):
            await interaction.response.send_message(
                "❌ You need to register first with `/register`.",
                ephemeral=True
            )
            return
        
        if database.has_responded_today(user_id):
            await interaction.response.send_message(
                "ℹ️ You've already submitted a standup today.\n"
                "Use `/edit_standup` to modify your responses.",
                ephemeral=True
            )
            return
        
        settings = database.get_settings()
        is_late = not database.is_within_collection_window()
        
        database.save_response(
            user_id=user_id,
            username=username,
            question_yesterday="No update",
            question_today="No update",
            blockers=None,
            confidence_mood=None,
            is_late=is_late
        )
        
        await interaction.response.send_message(
            "✅ **Noted!** You've been marked as having no update today.\n"
            "This counts as a completed standup.",
            ephemeral=True
        )
    
    @app_commands.command(name="list_users", description="[Admin] List all registered standup users")
    @app_commands.default_permissions(administrator=True)
    async def list_users(self, interaction: discord.Interaction):
        """Admin command to list all registered users."""
        users = database.get_registered_users()
        
        if not users:
            await interaction.response.send_message(
                "📭 No users are currently registered for standups.",
                ephemeral=True
            )
            return
        
        lines = [f"👥 **Registered Users** ({len(users)} total)\n"]
        
        for i, user in enumerate(users, 1):
            # Try to get Discord user for display name
            try:
                discord_user = await self.bot.fetch_user(int(user["user_id"]))
                name = f"{discord_user.mention} ({user['username']})"
            except Exception as e:
                logger.warning(f"Failed to fetch user {user['user_id']}: {e}")
                name = f"@{user['username']} (ID: {user['user_id']})"
            
            lines.append(f"{i}. {name}")
        
        await interaction.response.send_message(
            "\n".join(lines),
            ephemeral=True
        )

        # Individual timezone setting removed


async def setup(bot: commands.Bot):
    await bot.add_cog(RegistrationCog(bot))
