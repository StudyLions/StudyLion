# ============================================================
# AI-GENERATED FILE
# Created: 2026-03-20
# Purpose: aiohttp HTTP API routes for the test harness.
#          Accepts test requests and routes them through the
#          bot's command tree with mock interactions.
# ============================================================
import asyncio
import json
import logging
import traceback

from aiohttp import web

from .mock_interaction import build_mock_interaction

logger = logging.getLogger(__name__)

COMMAND_TIMEOUT = 15  # seconds


def create_app(bot) -> web.Application:
    app = web.Application()
    app['bot'] = bot

    app.router.add_get('/test/health', handle_health)
    app.router.add_get('/test/commands', handle_list_commands)
    app.router.add_post('/test/run', handle_run_command)

    return app


async def handle_health(request: web.Request) -> web.Response:
    bot = request.app['bot']
    data = {
        'status': 'ok',
        'ready': bot.is_ready(),
        'guilds': len(bot.guilds),
        'latency_ms': round(bot.latency * 1000, 1) if bot.latency else None,
        'cogs_loaded': list(bot.cogs.keys()),
        'shard_id': bot.shard_id,
    }
    return web.json_response(data)


def _serialize_param(param) -> dict:
    result = {'name': param.name, 'required': param.required}
    if hasattr(param, 'type') and hasattr(param.type, 'value'):
        result['type'] = param.type.value
    if hasattr(param, 'description'):
        result['description'] = str(param.description)[:200]
    if hasattr(param, 'choices') and param.choices:
        result['choices'] = [
            {'name': str(c.name), 'value': c.value}
            for c in param.choices
        ]
    return result


def _collect_commands(tree, prefix="") -> list[dict]:
    """Recursively collect all registered app commands."""
    commands = []
    for cmd in tree.get_commands():
        full_name = f"{prefix}{cmd.name}".strip()
        entry = {
            'name': full_name,
            'description': str(getattr(cmd, 'description', ''))[:200],
        }

        if hasattr(cmd, 'parameters'):
            entry['parameters'] = [_serialize_param(p) for p in cmd.parameters]
        else:
            entry['parameters'] = []

        if hasattr(cmd, 'commands'):
            for subcmd in cmd.commands:
                sub_entry = {
                    'name': f"{full_name} {subcmd.name}",
                    'description': str(getattr(subcmd, 'description', ''))[:200],
                }
                if hasattr(subcmd, 'parameters'):
                    sub_entry['parameters'] = [_serialize_param(p) for p in subcmd.parameters]
                else:
                    sub_entry['parameters'] = []

                if hasattr(subcmd, 'commands'):
                    for subsub in subcmd.commands:
                        subsub_entry = {
                            'name': f"{full_name} {subcmd.name} {subsub.name}",
                            'description': str(getattr(subsub, 'description', ''))[:200],
                        }
                        if hasattr(subsub, 'parameters'):
                            subsub_entry['parameters'] = [_serialize_param(p) for p in subsub.parameters]
                        else:
                            subsub_entry['parameters'] = []
                        commands.append(subsub_entry)
                else:
                    commands.append(sub_entry)
        else:
            commands.append(entry)

    return commands


async def handle_list_commands(request: web.Request) -> web.Response:
    bot = request.app['bot']
    commands = _collect_commands(bot.tree)
    return web.json_response({'commands': commands, 'count': len(commands)})


async def handle_run_command(request: web.Request) -> web.Response:
    bot = request.app['bot']

    try:
        body = await request.json()
    except Exception:
        return web.json_response({'error': 'Invalid JSON body'}, status=400)

    command_name = body.get('command')
    if not command_name:
        return web.json_response({'error': 'Missing "command" field'}, status=400)

    options = body.get('options', [])
    guild_id = body.get('guild_id')
    channel_id = body.get('channel_id')
    user_id = body.get('user_id')

    try:
        interaction, captured = await build_mock_interaction(
            bot, command_name,
            options=options,
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
        )
    except Exception as e:
        logger.exception("Failed to build mock interaction")
        return web.json_response({
            'error': f'Failed to build interaction: {e}',
            'traceback': traceback.format_exc(),
        }, status=500)

    error_info = None
    timed_out = False

    try:
        await asyncio.wait_for(
            bot.tree._call(interaction),
            timeout=COMMAND_TIMEOUT,
        )
    except asyncio.TimeoutError:
        timed_out = True
        error_info = f'Command timed out after {COMMAND_TIMEOUT}s'
    except Exception as e:
        error_info = repr(e)
        logger.info(f"Command '{command_name}' raised: {error_info}")

    result = {
        'command': command_name,
        'success': error_info is None and not timed_out,
        'timed_out': timed_out,
        'error': error_info,
        'responses': [r.to_dict() for r in captured],
        'response_count': len(captured),
        'command_failed': getattr(interaction, 'command_failed', False),
    }

    return web.json_response(result)
