"""Wolf CLI — Interactive terminal interface.

Usage:
    wolf                 # Start interactive REPL
    wolf -p "message"    # Single message mode
    wolf --version       # Show version
"""

import argparse
import sys
import os
import signal
import logging
from typing import Optional

# Suppress noisy logging before we configure it
logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger("wolf")


def _setup_logging(verbose: bool):
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)


def _print_banner(config=None):
    """Print the Wolf banner."""
    banner = """
\033[38;5;208m
 ██╗    ██╗ ██████╗ ██╗     ███████╗
 ██║    ██║██╔═══██╗██║     ██╔════╝
 ██║ █╗ ██║██║   ██║██║     █████╗
 ██║███╗██║██║   ██║██║     ██╔══╝
 ╚███╔███╔╝╚██████╔╝███████╗██║
  ╚══╝╚══╝  ╚═════╝ ╚══════╝╚═╝
\033[0m"""
    print(banner)
    print("  \033[1mWolf Agent\033[0m — Universal AI with top-tier coding")
    print("  Type \033[36m/help\033[0m for commands, \033[36m/quit\033[0m to exit\n")


def _print_help():
    """Print REPL help."""
    help_text = """
  Commands:
    /help              Show this help
    /quit, /exit       Exit Wolf
    /clear             Clear conversation history
    /tools             List available tools
    /agents            List available agents
    /agent <name>      Activate an agent (/agent off to deactivate)
    /agent             Show current agent status
    /skills            List loaded skills
    /permissions       Show permission rules
    /perm <tool> <lvl> Set permission (auto_allow/ask_once/ask_always/deny)
    /memory            Show memory contents
    /model             Show/switch model
    /version           Show Wolf version
    /usage             Show token usage

  Shortcuts:
    Ctrl+C         Interrupt current operation
    Ctrl+D         Exit Wolf
"""
    print(help_text)


def _get_user_input(prompt_toolkit_available: bool) -> Optional[str]:
    """Get user input with nice prompt."""
    try:
        if prompt_toolkit_available:
            from prompt_toolkit import prompt
            from prompt_toolkit.history import FileHistory
            from pathlib import Path
            history_path = Path.home() / ".wolf" / "history"
            history_path.parent.mkdir(parents=True, exist_ok=True)
            return prompt(
                "\033[38;5;208mwolf>\033[0m ",
                history=FileHistory(str(history_path)),
            )
        else:
            return input("\033[38;5;208mwolf>\033[0m ")
    except (KeyboardInterrupt, EOFError):
        return None


def _render_response(text: str, rich_available: bool):
    """Render assistant response."""
    from wolf.ui.renderer import render_response
    render_response(text)


def _stream_callback(chunk):
    """Handle streaming chunks — delegate to rich renderer."""
    from wolf.ui.renderer import create_stream_callback
    # This creates a new callback each time which is wasteful,
    # but it's simple. The callback is created once and reused.
    pass  # Will be replaced by create_stream_callback() in repl_loop


def _handle_command(cmd: str, agent) -> bool:
    """Handle slash commands. Returns True if handled."""
    cmd = cmd.strip().lower()

    if cmd in ("/quit", "/exit"):
        print("\033[38;5;208m🐺 Wolf out.\033[0m")
        return True

    if cmd == "/help":
        _print_help()
        return False

    if cmd == "/clear":
        agent._init_tools()
        agent.conversation_count = 0
        agent.active_agent = None
        print("\033[32m✓ Conversation cleared.\033[0m")
        return False

    if cmd == "/tools":
        from wolf.tools.registry import registry
        tools = registry.get_available_tools()
        print(f"\n  Available tools ({len(tools)}):")
        for t in tools:
            emoji = t.emoji or "🔧"
            print(f"    {emoji} {t.name:20s} — {t.description[:50]}")
        print()
        return False

    if cmd == "/skills":
        from wolf.skills.trigger import get_all_skills
        all_skills = get_all_skills()
        print(f"\n  All skills ({len(all_skills)}):")
        by_cat = {}
        for s in all_skills:
            cat = s.get("category", "other")
            by_cat.setdefault(cat, []).append(s)
        for cat in sorted(by_cat):
            print(f"\n  [{cat}]")
            for s in by_cat[cat]:
                desc = s.get("description", "")[:55]
                print(f"    📚 {s['name']:30s} {desc}")
        print()
        return False

    if cmd == "/permissions" or cmd == "/perms":
        from wolf.permissions import permission_manager
        print(permission_manager.format_rules_display())
        print()
        return False

    if cmd.startswith("/perm ") or cmd.startswith("/permissions "):
        from wolf.permissions import permission_manager
        parts = cmd.split(maxsplit=2)
        if len(parts) >= 3:
            tool, level = parts[1], parts[2]
            if level in ("auto_allow", "ask_once", "ask_always", "deny"):
                permission_manager.set_rule(tool, level)
                print(f"\n  ✅ {tool} → {level}\n")
            else:
                print(f"\n  ❌ Invalid level. Use: auto_allow, ask_once, ask_always, deny\n")
        else:
            print("\n  Usage: /perm <tool_name> <level>\n")
        return False

    if cmd == "/sessions" or cmd == "/session":
        from wolf.sessions import list_sessions
        sessions = list_sessions(limit=10)
        if sessions:
            print(f"\n  Recent sessions ({len(sessions)}):")
            for s in sessions:
                agent_info = s["metadata"].get("active_agent", "")
                agent_str = f" [{agent_info}]" if agent_info else ""
                print(f"    📂 {s['session_id']:15s} {s['created_at']:20s} "
                      f"{s['message_count']:3d} msgs{agent_str}")
            print(f"\n  Use /resume <session_id> to continue a session")
        else:
            print("\n  No saved sessions found.\n")
        print()
        return False

    if cmd.startswith("/resume "):
        sid = cmd[8:].strip()
        result = agent.resume_session(sid)
        print(f"\n  {result}\n")
        return False

    if cmd == "/agents":
        agents = agent.list_agents()
        print(f"\n  Available agents ({len(agents)}):")
        for a in agents:
            active = " \033[32m[ACTIVE]\033[0m" if agent.active_agent and agent.active_agent.name == a["name"] else ""
            print(f"    🤖 {a['name']:25s} — {a['description'][:60]}{active}")
        print()
        return False

    if cmd.startswith("/agent "):
        name = cmd[7:].strip()
        result = agent.set_agent(name)
        print(f"\n  {result}\n")
        return False

    if cmd == "/agent":
        if agent.active_agent:
            a = agent.active_agent
            print(f"\n  Active: {a.name}")
            print(f"  Model:  {a.model}")
            print(f"  Skills: {len(a.resolved_skills)} loaded")
            print(f"  Use /agent off to deactivate\n")
        else:
            print("\n  No agent active. Use /agents to list, /agent <name> to activate.\n")
        return False

    if cmd == "/memory":
        memory_path = agent.config.memory_path
        for fname in ["MEMORY.md", "USER.md"]:
            fpath = memory_path / fname
            if fpath.exists():
                content = fpath.read_text(encoding="utf-8")
                print(f"\n  === {fname} ===")
                print(f"  {content[:500]}")
        print()
        return False

    if cmd == "/model":
        print(f"\n  Provider: {agent.config.provider}")
        print(f"  Model:    {agent.model}")
        if agent.fallback_providers:
            print("  Fallback:")
            for p, m in agent.fallback_providers:
                print(f"    → {p.name}: {m}")
        print()
        return False

    if cmd == "/version":
        from wolf.agent import __version__
        print(f"\n  Wolf Agent v{__version__}\n")
        return False

    print(f"\033[31mUnknown command: {cmd}\033[0m")
    return False


def repl_loop(agent):
    """Main REPL loop."""
    _print_banner(agent.config)

    # Wire up interactive permission prompts
    from wolf.ui.prompts import permission_callback
    agent._permission_callback = permission_callback

    # Create stream callback for rich rendering
    from wolf.ui.renderer import create_stream_callback
    stream_cb = create_stream_callback()

    # Check available packages
    try:
        import prompt_toolkit
        pt_available = True
    except ImportError:
        pt_available = False

    # Show session info
    if agent.session_id:
        print(f"  \033[90mSession: {agent.session_id}\033[0m\n")

    while True:
        try:
            user_input = _get_user_input(pt_available)
            if user_input is None:
                print("\n\033[38;5;208m🐺 Wolf out.\033[0m")
                break

            user_input = user_input.strip()
            if not user_input:
                continue

            # Handle slash commands
            if user_input.startswith("/"):
                result = _handle_command(user_input, agent)
                if result:  # /quit
                    break
                continue

            # Process with agent
            response = agent.chat(user_input, callback=stream_cb)
            if response:
                _render_response(response, True)

        except KeyboardInterrupt:
            print("\n\033[33m(Interrupted)\033[0m")
            continue
        except EOFError:
            print("\n\033[38;5;208m🐺 Wolf out.\033[0m")
            break
        except Exception as e:
            logger.exception(f"Error in REPL: {e}")
            print(f"\n\033[31m✗ Error: {e}\033[0m")
            print("\033[90m  (Type /help for commands, /quit to exit)\033[0m")


def main():
    parser = argparse.ArgumentParser(
        prog="wolf",
        description="Wolf Agent — Universal AI with top-tier coding capabilities",
    )
    parser.add_argument("-p", "--print", dest="prompt", help="Single message mode (no REPL)")
    parser.add_argument("--model", help="Override model")
    parser.add_argument("--provider", help="Override provider")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    parser.add_argument("--version", action="version", version="Wolf Agent 1.1.0")
    parser.add_argument("command", nargs="?", default=None, help="setup")

    args = parser.parse_args()
    _setup_logging(args.verbose)

    # Handle setup wizard
    if args.command == "setup":
        from wolf.config.setup import run_setup
        run_setup()
        return

    from wolf.agent import WolfAgent
    from wolf.config.settings import load_config, ensure_wolf_dirs

    ensure_wolf_dirs()
    config = load_config()

    if args.model:
        config.model = args.model
    if args.provider:
        config.provider = args.provider

    # Validate API key availability
    api_key = config.providers.get(config.provider)
    if not api_key or not api_key.api_key:
        import os
        env_key = os.environ.get(f"{config.provider.upper()}_API_KEY",
                                 os.environ.get(f"WOLF_{config.provider.upper()}_API_KEY", ""))
        if not env_key:
            print(f"\n\033[31m✗ No API key found for provider '{config.provider}'.\033[0m")
            print(f"  Run \033[36mwolf setup\033[0m to configure, or set the environment variable:")
            print(f"  \033[33mexport {config.provider.upper()}_API_KEY=your-key-here\033[0m\n")
            return

    try:
        agent = WolfAgent(config=config)
    except Exception as e:
        print(f"\n\033[31m✗ Failed to initialize Wolf: {e}\033[0m")
        print(f"  Run \033[36mwolf setup\033[0m to reconfigure.\n")
        return

    if args.prompt is not None and args.prompt.strip():
        # Single message mode
        response = agent.chat(args.prompt)
        if response:
            _render_response(response, True)
    elif args.prompt is not None:
        # Empty prompt
        print("\033[33m⚠ Empty message. Usage: wolf -p \"your message\"\033[0m")
    else:
        # Interactive REPL
        repl_loop(agent)


if __name__ == "__main__":
    main()
