"""Skill Quality Scoring — Track usage and success rate of skills.

Each time a skill is used, record the outcome (success/failure).
Skills with low success rates are flagged for review or removal.
"""

import json
import time
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SCORES_FILE = Path.home() / ".wolf" / "memory" / "skill_scores.json"


def _load_scores() -> Dict[str, Dict[str, Any]]:
    """Load skill scores from disk."""
    if SCORES_FILE.exists():
        try:
            with open(SCORES_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_scores(scores: Dict[str, Dict[str, Any]]):
    """Save scores to disk."""
    SCORES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SCORES_FILE, "w") as f:
        json.dump(scores, f, indent=2)


def record_skill_use(skill_name: str, success: bool, context: str = ""):
    """Record a skill usage event."""
    scores = _load_scores()
    if skill_name not in scores:
        scores[skill_name] = {
            "uses": 0, "successes": 0, "failures": 0,
            "last_used": 0, "last_success": 0, "history": [],
        }

    entry = scores[skill_name]
    entry["uses"] += 1
    entry["last_used"] = time.time()

    if success:
        entry["successes"] += 1
        entry["last_success"] = time.time()
    else:
        entry["failures"] += 1

    # Keep last 20 history entries
    entry["history"].append({
        "time": time.time(),
        "success": success,
        "context": context[:100],
    })
    entry["history"] = entry["history"][-20:]

    _save_scores(scores)


def get_skill_score(skill_name: str) -> Dict[str, Any]:
    """Get quality score for a skill."""
    scores = _load_scores()
    if skill_name not in scores:
        return {"name": skill_name, "score": 0.5, "uses": 0, "status": "untested"}

    entry = scores[skill_name]
    uses = entry["uses"]
    successes = entry["successes"]
    success_rate = successes / uses if uses > 0 else 0.5

    # Score: weighted by usage recency and success rate
    recency_bonus = min(0.1, uses * 0.01)  # More usage = slight bonus
    score = success_rate * 0.9 + recency_bonus

    # Status
    if uses < 3:
        status = "untested"
    elif success_rate >= 0.8:
        status = "excellent"
    elif success_rate >= 0.5:
        status = "good"
    elif success_rate >= 0.3:
        status = "needs_review"
    else:
        status = "poor"

    return {
        "name": skill_name,
        "score": round(score, 2),
        "uses": uses,
        "success_rate": round(success_rate, 2),
        "status": status,
        "last_used": entry.get("last_used", 0),
    }


def get_all_scores() -> List[Dict[str, Any]]:
    """Get scores for all tracked skills."""
    scores = _load_scores()
    results = []
    for name in scores:
        results.append(get_skill_score(name))
    results.sort(key=lambda x: -x["score"])
    return results


def get_low_quality_skills(threshold: float = 0.3) -> List[Dict[str, Any]]:
    """Get skills with quality score below threshold."""
    all_scores = get_all_scores()
    return [s for s in all_scores if s["score"] < threshold and s["uses"] >= 3]


def rank_skills_for_query(skills: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Re-rank skills by combining relevance score with quality score."""
    for skill in skills:
        quality = get_skill_score(skill.get("name", ""))
        relevance = skill.get("_relevance_score", 1.0)
        skill["_quality_score"] = quality["score"]
        skill["_combined_score"] = relevance * 0.7 + quality["score"] * 0.3

    skills.sort(key=lambda x: -x.get("_combined_score", 0))
    return skills
