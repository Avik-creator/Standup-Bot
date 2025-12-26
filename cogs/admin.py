import discord
from discord.ext import commands
from discord import app_commands, ui
from tabulate import tabulate
from datetime import date
from typing import Optional
import pytz

import database
import gemini_client
import logging

logger = logging.getLogger(__name__)


# Common timezone options
TIMEZONE_OPTIONS = [
    ("UTC", "UTC"),
    ("US/Eastern", "US/Eastern"),
    ("US/Pacific", "US/Pacific"),
    ("Europe/London", "Europe/London"),
    ("Europe/Paris", "Europe/Paris"),
    ("Asia/Kolkata", "Asia/Kolkata"),
    ("Asia/Tokyo", "Asia/Tokyo"),
    ("Asia/Singapore", "Asia/Singapore"),
    ("Australia/Sydney", "Australia/Sydney"),
]

# Time options for dropdowns
HOUR_OPTIONS = [(f"{h:02d}:00", f"{h:02d}:00") for h in range(0, 24)]


class TimezoneSelect(ui.Select):
    """Dropdown for timezone selection."""
    
    def __init__(self):
        options = [
            discord.SelectOption(label=tz, value=tz) for label, tz in TIMEZONE_OPTIONS
        ]
        super().__init__(
            placeholder="Select your timezone...",
            options=options,
            min_values=1,
            max_values=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        timezone = self.values[0]
        database.set_timezone(timezone)
        settings = database.get_settings()
        
        await interaction.response.edit_message(
            content=(
                f"✅ **Timezone updated!**\n"
                f"🌍 Timezone: `{timezone}`\n"
                f"⏰ Collection: `{settings['start_time']}` - `{settings['end_time']}` ({timezone})"
            ),
            view=None
        )


class TimezoneView(ui.View):
    """View containing timezone dropdown."""
    
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(TimezoneSelect())


class StartTimeSelect(ui.Select):
    """Dropdown for start time selection."""
    
    def __init__(self):
        options = [
            discord.SelectOption(label=label, value=value) for label, value in HOUR_OPTIONS
        ]
        super().__init__(
            placeholder="Select start time...",
            options=options,
            min_values=1,
            max_values=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        self.view.start_time = self.values[0]
        await interaction.response.edit_message(
            content=f"📤 Start time: `{self.values[0]}`\n\nNow select the **end time**:",
            view=EndTimeView(self.values[0])
        )


class EndTimeSelect(ui.Select):
    """Dropdown for end time selection."""
    
    def __init__(self, start_time: str):
        self.start_time = start_time
        options = [
            discord.SelectOption(label=label, value=value) for label, value in HOUR_OPTIONS
        ]
        super().__init__(
            placeholder="Select end time...",
            options=options,
            min_values=1,
            max_values=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        end_time = self.values[0]
        database.set_settings(self.start_time, end_time)
        settings = database.get_settings()
        
        await interaction.response.edit_message(
            content=(
                f"✅ **Collection times updated!**\n"
                f"📤 Start: `{self.start_time}`\n"
                f"📥 End: `{end_time}`\n"
                f"🌍 Timezone: `{settings['timezone']}`"
            ),
            view=None
        )


class StartTimeView(ui.View):
    """View containing start time dropdown."""
    
    def __init__(self):
        super().__init__(timeout=60)
        self.start_time = None
        self.add_item(StartTimeSelect())


class EndTimeView(ui.View):
    """View containing end time dropdown."""
    
    def __init__(self, start_time: str):
        super().__init__(timeout=60)
        self.add_item(EndTimeSelect(start_time))


class ChannelSelect(ui.ChannelSelect):
    """Dropdown for summary channel selection."""
    
    def __init__(self):
        super().__init__(
            placeholder="Select a channel for summaries...",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        channel = self.values[0]
        database.set_summary_channel(str(channel.id))
        
        await interaction.response.edit_message(
            content=f"✅ **Summary channel set to {channel.mention}**\n\nDaily summaries will be posted there.",
            view=None
        )


class ChannelSelectView(ui.View):
    """View containing channel selection."""
    
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(ChannelSelect())


class AdminCog(commands.Cog):
    """Admin commands for managing standup collection."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(name="config", description="[Admin] View all standup bot configuration")
    @app_commands.default_permissions(administrator=True)
    async def view_config(self, interaction: discord.Interaction):
        """Show all current configuration."""
        settings = database.get_settings()
        registered_count = database.get_registered_user_count()
        
        # Get summary channel name
        summary_channel_text = "Not set"
        if settings["summary_channel_id"]:
            channel = interaction.guild.get_channel(int(settings["summary_channel_id"]))
            if channel:
                summary_channel_text = channel.mention
        
        config_text = (
            "⚙️ **Standup Bot Configuration**\n\n"
            "**Collection Settings:**\n"
            f"⏰ Times: `{settings['start_time']}` - `{settings['end_time']}`\n"
            f"🌍 Timezone: `{settings['timezone']}`\n"
            f"🔔 Reminders: {'Enabled' if settings['reminder_enabled'] else 'Disabled'}\n\n"
            "**Output:**\n"
            f"📢 Summary Channel: {summary_channel_text}\n\n"
            "**Users:**\n"
            f"👥 Registered: {registered_count} users\n\n"
            "**Commands:**\n"
            "`/set_time` - Change collection times\n"
            "`/set_timezone` - Change timezone\n"
            "`/set_summary_channel` - Set summary channel\n"
            "`/list_users` - View registered users"
        )
        
        await interaction.response.send_message(config_text, ephemeral=True)
    
    @app_commands.command(name="status", description="[Admin] View collection status for a date")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(date="Date in YYYY-MM-DD format (default: today)")
    async def view_status(self, interaction: discord.Interaction, date: Optional[str] = None):
        """Show collection status with responded vs missing breakdown."""
        from datetime import date as date_module
        
        settings = database.get_settings()
        target_date = date if date else database.get_standup_date(settings["timezone"])
        
        stats = database.get_response_stats(target_date)
        
        # Build status message
        total = stats["registered_count"]
        responded = stats["responded_count"]
        missing = stats["missing_count"]
        blocked = stats["blocked_count"]
        
        if total > 0:
            response_rate = (responded / total) * 100
        else:
            response_rate = 0
        
        status_lines = [
            f"📊 **Standup Status for {target_date}**\n",
            f"**Response Rate:** {responded}/{total} ({response_rate:.0f}%)\n",
            f"✅ Responded: {responded}",
            f"❌ Missing: {missing}",
            f"🚧 Blocked: {blocked}",
            f"⏰ Late: {stats['late_count']}\n",
        ]
        
        if stats["blocked_users"]:
            status_lines.append("**⚠️ Blocked Users:**")
            for user in stats["blocked_users"][:5]:  # Limit to 5
                status_lines.append(f"• {user['username']}: {user['blockers'][:50]}...")
        
        if stats["non_responders"]:
            status_lines.append(f"\n**❌ Missing Responses ({missing}):**")
            missing_names = [u["username"] for u in stats["non_responders"][:10]]
            status_lines.append(", ".join(missing_names))
            if missing > 10:
                status_lines.append(f"  _...and {missing - 10} more_")
        
        await interaction.response.send_message("\n".join(status_lines), ephemeral=True)
    
    @app_commands.command(name="missing", description="[Admin] List users who haven't responded")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(date="Date in YYYY-MM-DD format (default: today)")
    async def view_missing(self, interaction: discord.Interaction, date: Optional[str] = None):
        """Show detailed list of non-responders."""
        settings = database.get_settings()
        target_date = date if date else database.get_standup_date(settings["timezone"])
        
        non_responders = database.get_non_responders(target_date)
        
        if not non_responders:
            await interaction.response.send_message(
                f"✅ All registered users have responded for **{target_date}**!",
                ephemeral=True
            )
            return
        
        lines = [f"❌ **Missing Responses for {target_date}** ({len(non_responders)} total)\n"]
        
        for i, user in enumerate(non_responders, 1):
            try:
                discord_user = await self.bot.fetch_user(int(user["user_id"]))
                name = f"{discord_user.mention}"
            except:
                name = f"@{user['username']}"
            
            lines.append(f"{i}. {name}")
        
        lines.append("\n_Use `/collect_now` to send reminders to these users._")
        
        await interaction.response.send_message("\n".join(lines), ephemeral=True)
    
    @app_commands.command(name="set_time", description="[Admin] Set standup collection times")
    @app_commands.default_permissions(administrator=True)
    async def set_time(self, interaction: discord.Interaction):
        """Set collection start and end times via dropdown."""
        await interaction.response.send_message(
            "⏰ **Set Collection Times**\n\nSelect the **start time**:",
            view=StartTimeView(),
            ephemeral=True
        )
    
    @app_commands.command(name="set_timezone", description="[Admin] Set timezone for standup collection")
    @app_commands.default_permissions(administrator=True)
    async def set_timezone(self, interaction: discord.Interaction):
        """Set the timezone for collection times via dropdown."""
        await interaction.response.send_message(
            "🌍 **Set Timezone**\n\nSelect your timezone:",
            view=TimezoneView(),
            ephemeral=True
        )
    
    @app_commands.command(name="set_summary_channel", description="[Admin] Set channel for daily summaries")
    @app_commands.default_permissions(administrator=True)
    async def set_summary_channel(self, interaction: discord.Interaction):
        """Set the channel for posting daily summaries."""
        await interaction.response.send_message(
            "📢 **Set Summary Channel**\n\nSelect the channel where daily summaries will be posted:",
            view=ChannelSelectView(),
            ephemeral=True
        )
    
    @app_commands.command(name="responses", description="[Admin] View standup responses for a date")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(date="Date in YYYY-MM-DD format (default: today)")
    async def view_responses(self, interaction: discord.Interaction, date: Optional[str] = None):
        """View responses in a formatted list."""
        settings = database.get_settings()
        target_date = date if date else database.get_standup_date(settings["timezone"])
        
        responses = database.get_responses_for_date(target_date)
        
        if not responses:
            await interaction.response.send_message(
                f"📭 No responses found for **{target_date}**",
                ephemeral=True
            )
            return
        
        # Build response list
        response_lines = [f"📋 **Responses for {target_date}** ({len(responses)} total)\n"]
        
        for i, r in enumerate(responses, 1):
            yesterday = (r["question_yesterday"] or "N/A")[:60]
            today = (r["question_today"] or "N/A")[:60]
            blockers = r["blockers"] or "None"
            blockers = blockers[:40] if len(blockers) > 40 else blockers
            mood = f" | Mood: {r['confidence_mood']}/5" if r['confidence_mood'] else ""
            late = " ⏰" if r['is_late'] else ""
            edited = " ✏️" if r['edited_at'] else ""
            
            response_lines.append(
                f"**{i}. {r['username']}**{late}{edited}{mood}\n"
                f"> Yesterday: {yesterday}{'...' if len(r['question_yesterday'] or '') > 60 else ''}\n"
                f"> Today: {today}{'...' if len(r['question_today'] or '') > 60 else ''}\n"
                f"> Blockers: {blockers}\n"
            )
        
        # Split if too long
        full_text = "\n".join(response_lines)
        if len(full_text) > 2000:
            await interaction.response.send_message(
                f"📋 **Responses for {target_date}** ({len(responses)} total)",
                ephemeral=True
            )
            # Send in chunks
            chunk = ""
            for line in response_lines[1:]:
                if len(chunk) + len(line) > 1900:
                    await interaction.followup.send(chunk, ephemeral=True)
                    chunk = line
                else:
                    chunk += "\n" + line
            if chunk:
                await interaction.followup.send(chunk, ephemeral=True)
        else:
            await interaction.response.send_message(full_text, ephemeral=True)
    
    @app_commands.command(name="summary", description="[Admin] Generate AI summary for a date")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(date="Date in YYYY-MM-DD format (default: today)")
    async def generate_summary(self, interaction: discord.Interaction, date: Optional[str] = None):
        """Generate AI summary for a specific date."""
        settings = database.get_settings()
        target_date = date if date else database.get_standup_date(settings["timezone"])
        
        responses = database.get_responses_for_date(target_date)
        non_responders = database.get_non_responders(target_date)
        
        if not responses:
            await interaction.response.send_message(
                f"📭 No responses found for **{target_date}** - cannot generate summary",
                ephemeral=True
            )
            return
        
        await interaction.response.send_message("🤖 Generating summary with AI...", ephemeral=False)
        
        summary = gemini_client.generate_summary(responses, target_date, non_responders)
        
        # Post to summary channel if configured
        if settings["summary_channel_id"]:
            channel = interaction.guild.get_channel(int(settings["summary_channel_id"]))
            if channel:
                await channel.send(summary)
                await interaction.followup.send(f"✅ Summary posted to {channel.mention}")
                return
        
        await interaction.followup.send(summary)
    
    @app_commands.command(name="collect_now", description="[Admin] Manually trigger standup collection")
    @app_commands.default_permissions(administrator=True)
    async def collect_now(self, interaction: discord.Interaction):
        """Manually trigger standup collection."""
        collection_cog = self.bot.get_cog("CollectionCog")
        
        if not collection_cog:
            await interaction.response.send_message("❌ Collection system not available", ephemeral=True)
            return
        
        registered_count = database.get_registered_user_count()
        if registered_count == 0:
            await interaction.response.send_message(
                "📭 No users are registered for standups.\n"
                "Users need to run `/register` first.",
                ephemeral=True
            )
            return
        
        await interaction.response.send_message(
            f"📤 Starting standup collection for {registered_count} registered users...",
            ephemeral=False
        )
        
        count = await collection_cog.collect_from_registered_users(interaction.guild)
        
        await interaction.followup.send(f"✅ Sent DMs to **{count}** members")
    
    @app_commands.command(name="remind_now", description="[Admin] Send reminder to non-responders")
    @app_commands.default_permissions(administrator=True)
    async def remind_now(self, interaction: discord.Interaction):
        """Send reminder to users who haven't responded."""
        collection_cog = self.bot.get_cog("CollectionCog")
        
        if not collection_cog:
            await interaction.response.send_message("❌ Collection system not available", ephemeral=True)
            return
        
        non_responders = database.get_non_responders()
        if not non_responders:
            await interaction.response.send_message(
                "✅ All registered users have responded!",
                ephemeral=True
            )
            return
        
        await interaction.response.send_message(
            f"⏰ Sending reminders to {len(non_responders)} non-responders...",
            ephemeral=False
        )
        
        count = await collection_cog.send_reminders(interaction.guild)
        
        await interaction.followup.send(f"✅ Sent reminders to **{count}** members")
    
    @app_commands.command(name="standup_help", description="Show available standup bot commands")
    async def standup_help(self, interaction: discord.Interaction):
        """Show available commands."""
        settings = database.get_settings()
        
        help_text = (
            "📋 **Standup Bot Commands**\n\n"
            "**User Commands:**\n"
            "`/register` - Sign up for daily standups\n"
            "`/unregister` - Opt out of standups\n"
            "`/my_status` - Check your status\n"
            "`/no_update` - Mark no update for today\n"
            "`/edit_standup` - Edit your response\n\n"
            "**Admin Commands:**\n"
            "`/config` - View all settings\n"
            "`/status [date]` - View response status\n"
            "`/missing [date]` - List non-responders\n"
            "`/responses [date]` - View all responses\n"
            "`/summary [date]` - Generate AI summary\n"
            "`/collect_now` - Trigger collection\n"
            "`/remind_now` - Send reminders\n"
            "`/set_time` - Set collection times\n"
            "`/set_timezone` - Set timezone\n"
            "`/set_summary_channel` - Set summary channel\n"
            "`/list_users` - View registered users\n\n"
            "**Current Settings:**\n"
            f"⏰ Collection: `{settings['start_time']}` - `{settings['end_time']}`\n"
            f"🌍 Timezone: `{settings['timezone']}`"
        )
        
        await interaction.response.send_message(help_text, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
