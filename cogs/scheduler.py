import discord
from discord.ext import commands, tasks
from datetime import datetime
import os
import pytz

import database
import gemini_client


class SchedulerCog(commands.Cog):
    """Handles scheduled standup collection and summary generation."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guild_id = int(os.getenv("GUILD_ID", "0"))
        self.check_time_loop.start()
        self._last_collection_date = None
        self._last_reminder_date = None
        self._last_summary_date = None
    
    def cog_unload(self):
        self.check_time_loop.cancel()
    
    @tasks.loop(minutes=1)
    async def check_time_loop(self):
        """Check every minute if it's time to collect, remind, or summarize."""
        settings = database.get_settings()
        
        # Get current time in configured timezone
        tz = pytz.timezone(settings["timezone"])
        now = datetime.now(tz)
        current_time = now.strftime("%H:%M")
        current_date = now.date()
        
        start_time = settings["start_time"]
        end_time = settings["end_time"]
        
        # Calculate midpoint for reminder
        start_hour = int(start_time.split(":")[0])
        end_hour = int(end_time.split(":")[0])
        
        # Handle window spanning midnight
        if end_hour < start_hour:
            end_hour += 24
        mid_hour = ((start_hour + end_hour) // 2) % 24
        reminder_time = f"{mid_hour:02d}:00"
        
        # Check if it's collection start time
        if current_time == start_time and self._last_collection_date != current_date:
            self._last_collection_date = current_date
            await self._run_collection()
        
        # Check if it's reminder time (midpoint of window)
        if settings["reminder_enabled"]:
            if current_time == reminder_time and self._last_reminder_date != current_date:
                self._last_reminder_date = current_date
                await self._run_reminder()
        
        # Check if it's collection end time (generate summary)
        if current_time == end_time and self._last_summary_date != current_date:
            self._last_summary_date = current_date
            await self._run_summary()
    
    @check_time_loop.before_loop
    async def before_check_time_loop(self):
        """Wait until the bot is ready before starting the loop."""
        await self.bot.wait_until_ready()
    
    async def _run_collection(self):
        """Run the standup collection for registered users."""
        if self.guild_id == 0:
            print("[Scheduler] No GUILD_ID configured, skipping collection")
            return
        
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            print(f"[Scheduler] Guild {self.guild_id} not found")
            return
        
        collection_cog = self.bot.get_cog("CollectionCog")
        if not collection_cog:
            print("[Scheduler] CollectionCog not loaded")
            return
        
        registered_count = database.get_registered_user_count()
        if registered_count == 0:
            print("[Scheduler] No registered users, skipping collection")
            return
        
        print(f"[Scheduler] Starting scheduled collection for {guild.name} ({registered_count} registered users)")
        count = await collection_cog.collect_from_registered_users(guild)
        print(f"[Scheduler] Sent DMs to {count} members")
    
    async def _run_reminder(self):
        """Send reminders to non-responders."""
        if self.guild_id == 0:
            return
        
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            return
        
        collection_cog = self.bot.get_cog("CollectionCog")
        if not collection_cog:
            return
        
        non_responders = database.get_non_responders()
        if not non_responders:
            print("[Scheduler] All users have responded, no reminders needed")
            return
        
        print(f"[Scheduler] Sending reminders to {len(non_responders)} non-responders")
        count = await collection_cog.send_reminders(guild)
        print(f"[Scheduler] Sent reminders to {count} members")
    
    async def _run_summary(self):
        """Generate and post the daily summary."""
        if self.guild_id == 0:
            print("[Scheduler] No GUILD_ID configured, skipping summary")
            return
        
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            print(f"[Scheduler] Guild {self.guild_id} not found")
            return
        
        settings = database.get_settings()
        standup_date = database.get_standup_date(settings["timezone"])
        
        responses = database.get_responses_for_date(standup_date)
        non_responders = database.get_non_responders(standup_date)
        
        if not responses:
            print(f"[Scheduler] No responses for {standup_date}, skipping summary")
            return
        
        # Generate summary with non-responders
        summary = gemini_client.generate_summary(responses, standup_date, non_responders)
        
        # Post to configured summary channel, or find first available
        channel = None
        if settings["summary_channel_id"]:
            channel = guild.get_channel(int(settings["summary_channel_id"]))
        
        if not channel:
            # Fallback to first text channel with permissions
            for ch in guild.text_channels:
                if ch.permissions_for(guild.me).send_messages:
                    channel = ch
                    break
        
        if channel:
            await channel.send(summary)
            print(f"[Scheduler] Posted summary to #{channel.name}")
        else:
            print("[Scheduler] No channel available for summary")
    
    async def reschedule_jobs(self):
        """Called when admin updates time settings."""
        print("[Scheduler] Settings updated, new times will take effect next minute")


async def setup(bot: commands.Bot):
    await bot.add_cog(SchedulerCog(bot))
