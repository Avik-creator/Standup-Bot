from typing import List, Dict, Any, Optional
from google import genai
import logging

logger = logging.getLogger(__name__)

# Initialize client (uses GEMINI_API_KEY environment variable)
client = genai.Client()


def generate_summary(
    responses: List[Dict[str, Any]], 
    target_date: str,
    non_responders: Optional[List[Dict[str, Any]]] = None
) -> str:
    """
    Generate an AI summary of the day's standup responses.
    
    Args:
        responses: List of response dictionaries
        target_date: The date string for the summary
        non_responders: Optional list of users who didn't respond
    
    Returns:
        A formatted summary string
    """
    if not responses:
        return f"📋 **No responses collected for {target_date}**"
    
    # Build the responses text
    responses_text = ""
    blocked_users = []
    
    for r in responses:
        mood_str = f" (Mood: {r.get('confidence_mood', 'N/A')}/5)" if r.get('confidence_mood') else ""
        late_str = " [LATE]" if r.get('is_late') else ""
        
        responses_text += f"""
**{r['username']}**{late_str}{mood_str}
- Yesterday: {r.get('question_yesterday', 'N/A')}
- Today: {r.get('question_today', 'N/A')}
- Technical: {r.get('question_technical', 'None')}
- Blocker [{r.get('blocker_category') or 'None'}]: {r.get('blockers') or 'None'}
"""
        if r.get('blockers') and r['blockers'].lower() not in ['none', 'no', 'n/a']:
            blocked_users.append({
                "username": r['username'], 
                "category": r.get('blocker_category') or 'Other',
                "blocker": r['blockers']
            })
    
    # Build non-responders text
    non_responders_text = ""
    if non_responders:
        non_responders_text = "\n**Non-Responders:** " + ", ".join([u['username'] for u in non_responders])
    
    # Build blockers emphasis
    blockers_text = ""
    if blocked_users:
        blockers_text = "\n\n**BLOCKED USERS (REQUIRES ATTENTION):**\n"
        for u in blocked_users:
            blockers_text += f"- {u['username']} [{u['category']}]: {u['blocker']}\n"
    
    prompt = f"""You are a helpful assistant that summarizes daily standup responses for a software team.

Here are the standup responses for {target_date}:

{responses_text}
{blockers_text}
{non_responders_text}

Generate a STRUCTURED and ACTIONABLE summary following this EXACT format:

## 🎯 Today's Focus Areas
Group work by theme or feature area. List who is working on what.

## 🛠️ Technical Updates
Summarize the specific technical, architectural, or code-level changes mentioned. Be detailed but concise.
If NO technical updates, skip this section.

## ⚠️ Blockers (Immediate Attention Required)
List ALL blockers with the person's name and what they're blocked on.
If there are dependencies between team members, highlight them.
If someone is blocked on an external team, flag it clearly.
If NO blockers, write "✅ No blockers reported"

## 🚨 Risks & Dependencies  
Identify any risks based on the responses:
- People working on related features who may need to coordinate
- Tasks that depend on blocked work
- Patterns suggesting potential delays

## ❌ Missing Responses
{non_responders_text if non_responders else "✅ All registered users responded"}

RULES:
- **CRITICAL:** ONLY list people in the "Missing Responses" section if they are explicitly provided in the "Non-Responders" list above. 
- DO NOT assume someone is missing just because they are mentioned in someone else's response (e.g., if someone says "Discussed with Purna", DO NOT list Purna as missing unless he is in the provided list).
- DO NOT write generic summaries like "the team worked on various tasks"
- BE SPECIFIC with names and tasks
- HIGHLIGHT blockers prominently, including their CATEGORY (Technical, Process, Dependency, etc.).
- Group by theme/feature when multiple people work on related things
- Keep it concise but complete
- Use Discord markdown formatting (** for bold, - for bullets)
"""
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        
        # Stats header
        responded_count = len(responses)
        missing_count = len(non_responders) if non_responders else 0
        blocked_count = len(blocked_users)
        
        stats = f"📊 **{responded_count}** responded"
        if missing_count > 0:
            stats += f" | **{missing_count}** missing"
        if blocked_count > 0:
            stats += f" | **{blocked_count}** blocked"
        
        return f"📅 **Daily Standup Summary - {target_date}**\n{stats}\n\n{response.text}"
    except Exception as e:
        return f"❌ Error generating summary: {str(e)}"
