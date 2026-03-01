# ============================================================================
# FILE: action_generator.py
# LOCATION: src/
# PIPELINE POSITION: Step 4 - LLM reads boxes, generates action files, git-tracks diffs
# PURPOSE: Generate action items from box contents, track every LLM change in git
# ============================================================================
"""
Reads recently-updated memos in a category box, sends them to the LLM with the
existing action file, gets back an updated action file, and commits the diff
to a local git repo. Every LLM output is version-controlled.
"""

import subprocess
import logging
from pathlib import Path
from src.config_loader import Config
from src.llm_provider import LLMProvider
from src.event_logger import EventLogger

logger = logging.getLogger(__name__)


class ActionGenerator:
    """
    Generates action files per category box, tracks every change in git.
    All tuneable values come from config YAML files.
    """

    def __init__(self, config: Config, llm: LLMProvider,
                 event_logger: EventLogger, actions_dir: str):
        self.config = config
        self.llm = llm
        self.event_logger = event_logger
        self.actions_dir = Path(actions_dir)
        self._init_git_repo()

    def _init_git_repo(self):
        self.actions_dir.mkdir(parents=True, exist_ok=True)
        if not (self.actions_dir / ".git").exists():
            self._git("init")
            self._git("config", "user.email", self.config.git_user_email)
            self._git("config", "user.name", self.config.git_user_name)
            logger.info(f"Git repo initialized at {self.actions_dir}")

    def _git(self, *args) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git"] + list(args),
            cwd=self.actions_dir,
            capture_output=True,
            text=True,
        )

    async def generate(self, category_slug: str, category_description: str) -> dict:
        """
        Generate/update the action file for a category box.
        """
        action_file = self.actions_dir / f"{category_slug}.md"

        existing_actions = ""
        if action_file.exists():
            existing_actions = action_file.read_text()

        limit = self.config.recent_memos_limit
        recent = self.event_logger.get_recently_routed(category_slug, limit=limit)
        recent_text = "\n\n".join(
            f"[{m['updated_at']}] (uid: {m['memo_uid']})\n{m['preview']}"
            for m in recent
        )

        if not recent_text:
            logger.info(f"No recent memos in box '{category_slug}', skipping")
            return {"slug": category_slug, "diff": "", "commit_hash": "",
                    "actions": existing_actions}

        variables = {
            "category_slug": category_slug,
            "category_description": category_description,
            "recent_memos": recent_text,
            "existing_actions": existing_actions or "(no existing actions)",
        }

        prompt = self.config.get_prompt("action_generate", variables)

        model_cfg = self.config.llm_model_config("action_generate")
        result = await self.llm.complete(prompt, task="action_generate")

        if not result:
            logger.error(f"LLM returned nothing for '{category_slug}'")
            return {"slug": category_slug, "diff": "", "commit_hash": "",
                    "actions": existing_actions}

        action_file.write_text(result)
        self._git("add", f"{category_slug}.md")

        status = self._git("status", "--porcelain")
        if not status.stdout.strip():
            logger.info(f"No changes to action file for '{category_slug}'")
            return {"slug": category_slug, "diff": "", "commit_hash": "",
                    "actions": result}

        commit_msg = (
            f"update {category_slug}: {len(recent)} memo(s) processed\n\n"
            f"Box: {category_slug} ({category_description})\n"
            f"Model: {model_cfg['id']}\n"
            f"Temperature: {model_cfg['temperature']}\n"
            f"Max tokens: {model_cfg['max_tokens']}"
        )
        self._git("commit", "-m", commit_msg)

        diff_result = self._git("diff", "HEAD~1", "HEAD", "--", f"{category_slug}.md")
        hash_result = self._git("rev-parse", "--short", "HEAD")

        return {
            "slug": category_slug,
            "diff": diff_result.stdout,
            "commit_hash": hash_result.stdout.strip(),
            "actions": result,
        }

    def get_current_actions(self, category_slug: str) -> str:
        action_file = self.actions_dir / f"{category_slug}.md"
        return action_file.read_text() if action_file.exists() else ""

    def revert_last(self, category_slug: str) -> dict:
        log_result = self._git(
            "log", "--oneline", "-1", "--format=%H", "--", f"{category_slug}.md"
        )
        commit_hash = log_result.stdout.strip()
        if not commit_hash:
            return {"error": f"No commits found for {category_slug}.md"}

        revert_result = self._git("revert", "--no-edit", commit_hash)
        if revert_result.returncode != 0:
            return {"error": f"Revert failed: {revert_result.stderr}"}

        diff_result = self._git("diff", "HEAD~1", "HEAD", "--", f"{category_slug}.md")
        return {
            "slug": category_slug,
            "reverted_commit": commit_hash[:8],
            "diff": diff_result.stdout,
        }

    def get_history(self, category_slug: str, limit: int = None) -> list[dict]:
        effective_limit = limit if limit is not None else self.config.action_history_limit
        log_result = self._git(
            "log", f"-{effective_limit}", "--format=%H|%h|%s|%ai", "--", f"{category_slug}.md"
        )
        entries = []
        for line in log_result.stdout.strip().split("\n"):
            if "|" in line:
                parts = line.split("|", 3)
                entries.append({
                    "hash": parts[0], "short_hash": parts[1],
                    "message": parts[2], "date": parts[3] if len(parts) > 3 else "",
                })
        return entries

    def get_diff(self, commit_hash: str) -> str:
        result = self._git("show", "--stat", "--patch", commit_hash)
        return result.stdout
