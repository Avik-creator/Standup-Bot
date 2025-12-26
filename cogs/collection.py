import discord
from discord.ext import commands
from discord import app_commands, ui
from typing import Optional
import asyncio
import logging

logger = logging.getLogger(__name__)

import database


# Fixed standup questions
QUESTIONS = [
    ("question_yesterday", "📋 **What did you work on yesterday?**\n(Describe completed tasks)"),
    ("question_today", "🎯 **What are you working on today?**\n(Describe your plans)"),
    ("question_technical", "🛠️ **Any technical updates?**\n(Specific architectural or code changes)"),
    ("blocker_category", None),  # Step 3: Select category
    ("blockers", None),          # Step 4: Type details
    ("confidence_mood", None),   # Step 5: Mood
]


# Predefined blocker categories
BLOCKER_CATEGORIES = [
    ("No blockers", "None"),
    ("Technical issue", "Technical"),
    ("Process/Workstream", "Process"),
    ("Waiting on someone", "Dependency"),
    ("Scheduling/Time", "Scheduling"),
    ("Other", "Other"),
]


class MoodButton(ui.Button):
    """Button for mood/confidence selection."""
    
    def __init__(self, value: int, emoji: str, session: dict):
        super().__init__(style=discord.ButtonStyle.secondary, emoji=emoji, custom_id=f"mood_{value}")
        self.value = value
        self.session = session
    
    async def callback(self, interaction: discord.Interaction):
        # Save the response
        database.save_response(
            user_id=str(interaction.user.id),
            username=interaction.user.name,
            question_yesterday=self.session["responses"]["question_yesterday"],
            question_today=self.session["responses"]["question_today"],
            question_technical=self.session["responses"].get("question_technical"),
            blocker_category=self.session["responses"].get("blocker_category"),
            blockers=self.session["responses"].get("blockers"),
            confidence_mood=self.value,
            is_late=self.session.get("is_late", False)
        )
        
        mood_emojis = {1: "😟", 2: "😕", 3: "😐", 4: "🙂", 5: "😊"}
        
        # Build summary
        summary_lines = [
            "✅ **Standup Complete!** Thank you for your response.\n",
            "📊 **Your Summary:**",
            f"**Yesterday:** {self.session['responses']['question_yesterday'][:100]}...",
            f"**Today:** {self.session['responses']['question_today'][:100]}...",
            f"**Technical:** {self.session['responses'].get('question_technical', 'None')[:50]}...",
            f"**Blocker:** [{self.session['responses'].get('blocker_category') or 'None'}] {self.session['responses'].get('blockers') or 'N/A'}",
            f"**Mood:** {mood_emojis.get(self.value, '?')} ({self.value}/5)",
            "\nHave a productive day! 🚀"
        ]
        
        await interaction.response.edit_message(
            content="\n".join(summary_lines),
            view=None
        )
        
        self.session["complete"] = True


class MoodView(ui.View):
    """View for mood/confidence selection."""
    
    def __init__(self, session: dict):
        super().__init__(timeout=300)
        self.session = session
        
        moods = [(1, "😟"), (2, "😕"), (3, "😐"), (4, "🙂"), (5, "😊")]
        for value, emoji in moods:
            self.add_item(MoodButton(value, emoji, session))
    
    @ui.button(label="Skip", style=discord.ButtonStyle.grey, row=1)
    async def skip_button(self, interaction: discord.Interaction, button: ui.Button):
        # Save without mood
        database.save_response(
            user_id=str(interaction.user.id),
            username=interaction.user.name,
            question_yesterday=self.session["responses"]["question_yesterday"],
            question_today=self.session["responses"]["question_today"],
            question_technical=self.session["responses"].get("question_technical"),
            blocker_category=self.session["responses"].get("blocker_category"),
            blockers=self.session["responses"].get("blockers"),
            confidence_mood=None,
            is_late=self.session.get("is_late", False)
        )
        
        summary_lines = [
            "✅ **Standup Complete!** Thank you for your response.\n",
            "📊 **Your Summary:**",
            f"**Yesterday:** {self.session['responses']['question_yesterday'][:100]}...",
            f"**Today:** {self.session['responses']['question_today'][:100]}...",
            f"**Blockers:** {self.session['responses'].get('blockers') or 'None'}",
            "\nHave a productive day! 🚀"
        ]
        
        await interaction.response.edit_message(
            content="\n".join(summary_lines),
            view=None
        )
        
        self.session["complete"] = True


class BlockerSelect(ui.Select):
    """Dropdown for blocker options."""
    
    def __init__(self, session: dict):
        self.session = session
        options = [
            discord.SelectOption(
                label=label, 
                value=value,
                description=f"Category: {value}" if value != "None" else "No blockers"
            )
            for label, value in BLOCKER_CATEGORIES
        ]
        
        super().__init__(
            placeholder="Select a blocker category...",
            options=options,
            min_values=1,
            max_values=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        self.session["responses"]["blocker_category"] = selected
        
        if selected == "None":
            self.session["responses"]["blockers"] = "None"
            self.session["step"] = 5  # Skip step 4 (details)
            
            # Save partial
            database.save_partial_response(
                user_id=self.session["user_id"],
                username=self.session["username"],
                step=5,
                blocker_category="None",
                blockers="None"
            )
            
            # Show mood selection
            await interaction.response.edit_message(
                content=(
                    f"📊 Progress: 5/6 questions answered\n\n"
                    "🎭 **How are you feeling today?** (Optional)\n\n"
                    "Rate your confidence/mood (1-5):"
                ),
                view=MoodView(self.session)
            )
        else:
            self.session["step"] = 4
            
            # Save partial
            database.save_partial_response(
                user_id=self.session["user_id"],
                username=self.session["username"],
                step=4,
                blocker_category=selected
            )
            
            await interaction.response.edit_message(
                content=(
                    f"📊 Progress: 4/6 questions answered\n\n"
                    f"🚧 **You selected '{selected}' blocker.**\n"
                    "Please type the specific details of your blocker below:"
                ),
                view=None
            )


class BlockerView(ui.View):
    """View containing blocker dropdown."""
    
    def __init__(self, session: dict):
        super().__init__(timeout=300)
        self.session = session
        self.add_item(BlockerSelect(session))


class NoUpdateView(ui.View):
    """View with 'No update today' option."""
    
    def __init__(self, session: dict):
        super().__init__(timeout=300)
        self.session = session
    
    @ui.button(label="No update today", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def no_update_button(self, interaction: discord.Interaction, button: ui.Button):
        database.save_response(
            user_id=str(interaction.user.id),
            username=interaction.user.name,
            question_yesterday=self.session["responses"].get("question_yesterday") or "No update",
            question_today=self.session["responses"].get("question_today") or "No update",
            question_technical="None",
            blocker_category="None",
            blockers="None",
            confidence_mood=None,
            is_late=self.session.get("is_late", False)
        )
        
        await interaction.response.edit_message(
            content="✅ **Noted!** You've been marked as having no update today.",
            view=None
        )
        
        self.session["complete"] = True


class EditFieldSelect(ui.Select):
    """Dropdown for selecting which field to edit."""
    
    def __init__(self, response: dict):
        self.response = response
        options = [
            discord.SelectOption(label="Yesterday's work", value="question_yesterday"),
            discord.SelectOption(label="Today's work", value="question_today"),
            discord.SelectOption(label="Technical updates", value="question_technical"),
            discord.SelectOption(label="Blocker Category", value="blocker_category"),
            discord.SelectOption(label="Blocker Details", value="blockers"),
        ]
        
        super().__init__(
            placeholder="Select field to edit...",
            options=options,
            min_values=1,
            max_values=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        field = self.values[0]
        field_labels = {
            "question_yesterday": "yesterday's work",
            "question_today": "today's work",
            "question_technical": "technical updates",
            "blocker_category": "blocker category",
            "blockers": "blocker details"
        }
        
        current_value = self.response.get(field) or "None"
        
        await interaction.response.send_modal(
            EditFieldModal(field, field_labels[field], current_value, self.response["standup_date"])
        )


class EditFieldModal(ui.Modal):
    """Modal for editing a response field."""
    
    def __init__(self, field: str, field_label: str, current_value: str, standup_date: str):
        super().__init__(title=f"Edit {field_label}")
        self.field = field
        self.standup_date = standup_date
        
        self.new_value = ui.TextInput(
            label=f"New value for {field_label}",
            style=discord.TextStyle.paragraph,
            default=current_value if current_value != "None" else "",
            required=True,
            max_length=1000
        )
        self.add_item(self.new_value)
    
    async def on_submit(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        value = self.new_value.value if self.new_value.value else None
        
        success = database.update_response_field(
            user_id=user_id,
            standup_date=self.standup_date,
            field=self.field,
            value=value
        )
        
        if success:
            await interaction.response.send_message(
                f"✅ Updated your {self.field.replace('_', ' ')}!",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ Failed to update. You may not have a response for today.",
                ephemeral=True
            )


class EditView(ui.View):
    """View for editing responses."""
    
    def __init__(self, response: dict):
        super().__init__(timeout=120)
        self.add_item(EditFieldSelect(response))


class CollectionCog(commands.Cog):
    """Handles standup response collection via DMs."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_sessions: dict[int, dict] = {}  # user_id -> session data
    
    async def collect_from_member(self, member: discord.Member, reminder: bool = False) -> bool:
        """Send DM and collect standup responses from a single member."""
        if member.bot:
            return False
        
        user_id = str(member.id)
        
        # Only collect from registered users
        if not database.is_user_registered(user_id):
            return False
        
        if database.has_responded_today(user_id):
            return False
        
        try:
            dm_channel = await member.create_dm()
        except discord.Forbidden:
            logger.warning(f"Cannot DM {member.name} - DMs disabled")
            return False
        
        settings = database.get_settings()
        is_late = not database.is_within_collection_window()
        
        # Check for partial response to resume
        partial = database.get_partial_response(user_id)
        
        # Start/resume collection session
        self.active_sessions[member.id] = {
            "user_id": user_id,
            "username": member.name,
            "step": partial["current_step"] if partial else 0,
            "responses": {
                "question_yesterday": partial["question_yesterday"] if partial else None,
                "question_today": partial["question_today"] if partial else None,
                "question_technical": partial["question_technical"] if partial else None,
                "blocker_category": partial["blocker_category"] if partial else None,
                "blockers": partial["blockers"] if partial else None,
            } if partial else {},
            "channel": dm_channel,
            "awaiting_custom_blocker": False,
            "complete": False,
            "is_late": is_late
        }
        
        session = self.active_sessions[member.id]
        
        # Send intro
        if partial:
            intro = (
                "👋 **Welcome back!** Let's continue your standup.\n\n"
                f"📊 Progress: {partial['current_step']}/6 questions answered\n\n"
            )
        else:
            intro = (
                "👋 **Daily Standup Time!**\n\n"
                "Please answer the following questions. You can:\n"
                "• Answer at your own pace (progress is saved)\n"
                "• Use `/edit_standup` later to modify answers\n"
                "• Click 'No update today' to skip\n\n"
                "📊 Progress: 0/6 questions answered\n\n"
            )
        
        if reminder:
            intro = "⏰ **Reminder:** " + intro
        
        # Send first unanswered question
        if session["step"] == 0:
            view = NoUpdateView(session)
            await dm_channel.send(
                intro + QUESTIONS[0][1],
                view=view
            )
        elif session["step"] == 1:
            await dm_channel.send(intro + QUESTIONS[1][1])
        elif session["step"] == 2:
            await dm_channel.send(intro + QUESTIONS[2][1])
        elif session["step"] == 3:
            await dm_channel.send(
                intro + "🚧 **Select the category of your blocker:**",
                view=BlockerView(session)
            )
        elif session["step"] == 4:
            await dm_channel.send(
                intro + f"🚧 **You selected '{session['responses'].get('blocker_category')}' blocker.**\n"
                "Please type the specific details of your blocker:"
            )
        elif session["step"] == 5:
            await dm_channel.send(
                intro + "🎭 **How are you feeling today?** (Optional)",
                view=MoodView(session)
            )
        
        return True
    
    async def collect_from_registered_users(self, guild: discord.Guild) -> int:
        """Send DMs to all registered members. Returns count of DMs sent."""
        registered = database.get_registered_users()
        count = 0
        
        for user_data in registered:
            try:
                member = guild.get_member(int(user_data["user_id"]))
                if member and await self.collect_from_member(member):
                    count += 1
                    await asyncio.sleep(1)  # Rate limiting
            except Exception as e:
                logger.error(f"Error sending to {user_data['username']}: {e}")
        
        return count
    
    async def send_reminders(self, guild: discord.Guild) -> int:
        """Send reminders to non-responders. Returns count sent."""
        non_responders = database.get_non_responders()
        count = 0
        
        for user_data in non_responders:
            try:
                member = guild.get_member(int(user_data["user_id"]))
                if member and await self.collect_from_member(member, reminder=True):
                    count += 1
                    await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Error sending reminder to {user_data['username']}: {e}")
        
        return count
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle DM responses from active sessions."""
        if message.author.bot:
            return
        
        if not isinstance(message.channel, discord.DMChannel):
            return
        
        user_id = message.author.id
        
        if user_id not in self.active_sessions:
            return
        
        session = self.active_sessions[user_id]
        
        if session.get("complete"):
            del self.active_sessions[user_id]
            return
        
        step = session["step"]
        
        # No longer using session.get("awaiting_custom_blocker") 
        # as the flow is now deterministic based on step 4
        
        # Store response based on current step
        if step == 0:
            session["responses"]["question_yesterday"] = message.content
            session["step"] = 1
            
            # Save partial
            database.save_partial_response(
                user_id=session["user_id"],
                username=session["username"],
                step=1,
                question_yesterday=message.content
            )
            
            await message.channel.send(
                "📊 Progress: 1/6 questions answered\n\n" + QUESTIONS[1][1]
            )
            
        elif step == 1:
            session["responses"]["question_today"] = message.content
            session["step"] = 2
            
            # Save partial
            database.save_partial_response(
                user_id=session["user_id"],
                username=session["username"],
                step=2,
                question_today=message.content
            )
            
            await message.channel.send(
                "📊 Progress: 2/6 questions answered\n\n" + QUESTIONS[2][1]
            )
        elif step == 2:
            session["responses"]["question_technical"] = message.content
            session["step"] = 3
            
            # Save partial
            database.save_partial_response(
                user_id=session["user_id"],
                username=session["username"],
                step=3,
                question_technical=message.content
            )
            
            await message.channel.send(
                "📊 Progress: 3/6 questions answered\n\n"
                "🚧 **Select the category of your blocker:**",
                view=BlockerView(session)
            )
        elif step == 3:
            # Step 3 handled by BlockerView callback
            pass
        elif step == 4:
            session["responses"]["blockers"] = message.content
            session["step"] = 5
            
            # Save partial
            database.save_partial_response(
                user_id=session["user_id"],
                username=session["username"],
                step=5,
                blockers=message.content
            )
            
            await message.channel.send(
                "📊 Progress: 5/6 questions answered\n\n"
                "🎭 **How are you feeling today?** (Optional)\n\n"
                "Rate your confidence/mood (1-5):",
                view=MoodView(session)
            )
    
    @app_commands.command(name="edit_standup", description="Edit your standup response for today")
    async def edit_standup(self, interaction: discord.Interaction):
        """Allow user to edit their standup response."""
        user_id = str(interaction.user.id)
        
        if not database.is_user_registered(user_id):
            await interaction.response.send_message(
                "❌ You need to register first with `/register`.",
                ephemeral=True
            )
            return
        
        response = database.get_user_response(user_id)
        
        if not response:
            await interaction.response.send_message(
                "❌ You haven't submitted a standup today.\n"
                "Wait for the collection DM or use `/no_update` if you have nothing to report.",
                ephemeral=True
            )
            return
        
        # Check if within window
        if not database.is_within_collection_window():
            await interaction.response.send_message(
                "⚠️ The collection window is closed. Edits are only allowed during the collection window.",
                ephemeral=True
            )
            return
        
        # Show current response and edit options
        response_lines = [
            "📝 **Your Current Standup Response**\n",
            f"**Yesterday:** {response['question_yesterday'] or 'None'}",
            f"**Today:** {response['question_today'] or 'None'}",
            f"**Technical:** {response['question_technical'] or 'None'}",
            f"**Blocker Category:** {response['blocker_category'] or 'None'}",
            f"**Blocker Details:** {response['blockers'] or 'None'}",
            f"**Mood:** {response['confidence_mood'] or 'Not set'}/5" if response['confidence_mood'] else "",
            "\nSelect a field to edit:"
        ]
        
        await interaction.response.send_message(
            "\n".join([l for l in response_lines if l]),
            view=EditView(response),
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(CollectionCog(bot))
