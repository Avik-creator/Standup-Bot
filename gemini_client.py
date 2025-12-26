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
    
    # Build raw input for AI
    responses_text = ""
    blocked_users = []
    
    for r in responses:
        late_str = " (LATE)" if r.get('is_late') else ""
        mood_str = f" [Mood: {r['confidence_mood']}/5]" if r.get('confidence_mood') else ""
        
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
    
    # 1. Raw Non-Responders for logic and input
    missing_list_str = "\n".join([f"- {u['username']}" for u in non_responders]) if non_responders else ""
    non_responders_input = "### NON-RESPONDERS:\n" + (missing_list_str if missing_list_str else "- None")
    
    # 2. Raw Blockers for input
    blockers_input = "### BLOCKS:\n"
    if blocked_users:
        for u in blocked_users:
            blockers_input += f"- {u['username']} [{u['category']}]: {u['blocker']}\n"
    else:
        blockers_input += "- None reported\n"
    
    prompt = f"""You are an experienced Engineering Manager preparing a DAILY STANDUP REPORT for leadership.
This summary will be read by founders and tech leads — clarity and accountability matter.

Below are raw standup responses for {target_date}. Your job is to transform them into a
CLEAR, STRUCTURED, ACTIONABLE report.

INPUT:
{responses_text}
{blockers_input}
{non_responders_input}

---

OUTPUT REQUIREMENTS
You MUST follow the format below EXACTLY.
Do NOT add extra sections.
Do NOT add commentary outside the sections.
Do NOT use vague or motivational language.

---

## 🎯 Today's Focus Areas
- Group work by FEATURE, MODULE, or INITIATIVE (not by person).
- Under each group, list:
  - Person name
  - Exact task or outcome they are working on
- If someone’s update is vague, rewrite it into a concrete task without inventing facts.

## 🛠️ Technical Updates
- Include ONLY concrete technical details:
  - Code changes, APIs, infra, architecture, bugs, refactors, tooling
- Mention technologies, systems, or components explicitly when available.
- If there are NO meaningful technical updates, OMIT this section entirely.

## ⚠️ Blockers (Immediate Attention Required)
- List EVERY blocker explicitly.
- Format each blocker as:
  - **Name** — [{'{CATEGORY}'}]: blocker description
- Highlight:
  - Dependencies on other team members
  - Dependencies on external teams or systems
- If NO blockers exist, write exactly:
  ✅ No blockers reported

## 🚨 Risks & Dependencies
Identify REAL risks based ONLY on the provided data:
- Parallel work that may conflict or require coordination
- Work blocked by unresolved dependencies
- Patterns suggesting schedule or delivery risk
DO NOT speculate beyond the responses.

## ❌ Missing Responses
{missing_list_str if non_responders else "✅ All registered users responded"}

---

STRICT RULES (NON-NEGOTIABLE):
- ONLY list names in “Missing Responses” if they are explicitly provided above.
- DO NOT assume someone is missing based on mentions in other updates.
- DO NOT write generic phrases like:
  - “The team worked on various tasks”
  - “Progress is being made”
- DO NOT invent work, blockers, or risks.
- Be concise, factual, and execution-focused.
- Use Discord markdown ONLY (**bold**, - bullets).
"""
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        
        return f"📅 **Daily Standup Summary - {target_date}**\n\n{response.text}"
    except Exception as e:
        return f"❌ Error generating summary: {str(e)}"
