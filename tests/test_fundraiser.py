# ============================================================
# AI-GENERATED FILE
# Created: 2026-09-10
# Purpose: Exercise fundraiser payloads and public response hooks against
#          real discord.py, with a fake HTTP adapter and no Discord traffic.
# Run directly: python tests/test_fundraiser.py (bypasses legacy pytest stubs).
# ============================================================
import importlib.util
import io
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
from discord.webhook.async_ import async_context
from discord.utils import MISSING

if not isinstance(getattr(discord, '__version__', None), str):
    raise unittest.SkipTest('Run directly with real discord.py; legacy conftest stubs it.')

path = Path(__file__).resolve().parents[1] / 'src/modules/fundraiser/responses.py'
spec = importlib.util.spec_from_file_location('fundraiser_responses', path)
fundraiser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fundraiser)


class PayloadTests(unittest.TestCase):
    def test_embed_cards_preserved_without_mutating_original(self):
        card = discord.Embed(title='Profile').set_image(url='attachment://profile.png')
        stats = discord.Embed(description='Statistics').set_footer(text='Page 1 of 2')
        original = [card, stats]
        payload, mode = fundraiser.add_notice({'embeds': original})
        self.assertEqual(mode, 'embed')
        self.assertEqual(len(original), 2)
        self.assertEqual(payload['embeds'][:2], original)
        self.assertEqual(card.image.url, 'attachment://profile.png')
        again, _ = fundraiser.add_notice(payload, editing=True, previous=mode)
        self.assertEqual(len(again['embeds']), 3)

    def test_limits_and_no_truncation(self):
        original = [discord.Embed(description='x') for _ in range(10)]
        payload, mode = fundraiser.add_notice({'embeds': original, 'content': 'Result'})
        self.assertEqual(mode, 'content')
        self.assertEqual(payload['embeds'], original)
        self.assertTrue(payload['content'].startswith('Result\n\n'))
        full = {'embeds': original, 'content': 'x' * 2000}
        self.assertEqual(fundraiser.add_notice(full)[0], full)

    def test_aggregate_embed_limits_include_unicode_fields(self):
        remaining = 6000 - fundraiser._units(fundraiser.NOTICE)
        card = discord.Embed(description='x' * (remaining - 4))
        card.add_field(name='😀', value='😀')
        payload, mode = fundraiser.add_notice({'embed': card})
        self.assertEqual(mode, 'embed')
        self.assertEqual(len(payload['embeds']), 2)
        card.description += 'x'
        payload, mode = fundraiser.add_notice({'embed': card})
        self.assertEqual(mode, 'content')
        self.assertIs(payload['embed'], card)

    def test_content_unicode_boundary(self):
        remaining = 2000 - fundraiser._units(fundraiser.CONTENT_NOTICE) - 2
        text = '😀' * (remaining // 2) + 'x' * (remaining % 2)
        full_embeds = [discord.Embed(description='x') for _ in range(10)]
        payload, _ = fundraiser.add_notice({'content': text, 'embeds': full_embeds})
        self.assertEqual(fundraiser._units(payload['content']), 2000)
        payload, _ = fundraiser.add_notice({'content': text + '😀', 'embeds': full_embeds})
        self.assertEqual(payload['content'], text + '😀')

    def test_omitted_fields_and_cleanup_preserve_original(self):
        for payload in ({'view': None}, {'attachments': []}, {'content': 'Page 2'}):
            actual, _ = fundraiser.add_notice(payload, editing=True, previous='embed')
            self.assertEqual(actual, payload)
        unknown = {'attachments': []}
        self.assertEqual(fundraiser.add_notice(unknown, editing=True)[0], unknown)

    def test_deferred_first_card_gets_notice(self):
        attachment = object()
        payload, mode = fundraiser.add_notice({'attachments': [attachment]}, editing=True, previous='empty')
        self.assertEqual(mode, 'embed')
        self.assertEqual(payload['attachments'], [attachment])
        self.assertEqual(len(payload['embeds']), 1)

    def test_saturated_edit_does_not_overwrite_omitted_content(self):
        payload = {'embeds': [discord.Embed(description='x') for _ in range(10)]}
        self.assertEqual(fundraiser.add_notice(payload, editing=True)[0], payload)

    def test_content_fallback_remains_single_on_edits(self):
        payload, mode = fundraiser.add_notice({'embeds': [discord.Embed()] * 10, 'content': 'Result'})
        again, _ = fundraiser.add_notice(payload, editing=True, previous=mode)
        self.assertEqual(again['content'].count(fundraiser.CONTENT_NOTICE), 1)
        updated, _ = fundraiser.add_notice({'content': 'Updated'}, editing=True, previous=mode)
        self.assertTrue(updated['content'].startswith('Updated\n\n'))

    def test_conflicting_embed_arguments_still_reach_discord_validation(self):
        payload = {'embed': discord.Embed(), 'embeds': []}
        self.assertEqual(fundraiser.add_notice(payload)[0], payload)

    def test_missing_embed_permission_uses_content(self):
        payload, mode = fundraiser.add_notice({'content': 'Your result'}, allow_embed=False)
        self.assertEqual(mode, 'content')
        self.assertNotIn('embeds', payload)
        self.assertTrue(payload['content'].startswith('Your result\n\n'))

    def test_unknown_partial_edits_preserve_all_omitted_fields(self):
        for payload in ({'content': 'New text'}, {'embed': discord.Embed(title='New card')}, {'attachments': []}):
            actual, _ = fundraiser.add_notice(payload, editing=True, previous='unknown')
            self.assertEqual(actual, payload)


class ResponseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = discord.Client(intents=discord.Intents.none())
        self.state = self.client._connection
        self.user_data = {'id': '987654321', 'username': 'Leo', 'discriminator': '0', 'avatar': None, 'bot': True}
        self.state.user = discord.ClientUser(state=self.state, data=self.user_data)
        self.messages = {}
        self.deferred_tokens = set()
        self.last_payload = None
        self.counter = 400000000000000001
        self.adapter = SimpleNamespace(
            create_interaction_response=AsyncMock(side_effect=self.response),
            execute_webhook=AsyncMock(side_effect=self.followup),
            edit_original_interaction_response=AsyncMock(side_effect=self.edit_original),
            edit_webhook_message=AsyncMock(side_effect=self.edit_webhook),
        )
        self.adapter_token = async_context.set(self.adapter)
        self.hooks = fundraiser.FundraiserResponses(self.client)
        self.hooks.install()

    async def asyncTearDown(self):
        self.hooks.uninstall()
        async_context.reset(self.adapter_token)
        await self.client.close()

    def interaction(self, token='test-only-token', type=2, message=None):
        data = {
            'id': str(self.counter), 'application_id': '987654321', 'token': token,
            'version': 1, 'type': type, 'locale': 'en-US', 'attachment_size_limit': 10485760,
            'data': {'id': '123', 'name': 'profile', 'type': 1},
            'user': {'id': '123456789', 'username': 'Ari', 'discriminator': '0', 'avatar': None},
            'channel': {'id': '123456789', 'type': 1, 'recipients': []},
        }
        if message:
            data['message'] = message
        return discord.Interaction(data=data, state=self.state)

    def message(self, payload, key):
        self.counter += 1
        previous = self.messages.get(key, {})
        result = {
            'id': previous.get('id', str(self.counter)), 'channel_id': '123456789',
            'author': self.user_data, 'content': previous.get('content', ''),
            'embeds': previous.get('embeds', []), 'attachments': [],
            'timestamp': '2026-09-10T12:00:00+00:00', 'type': 0,
            'flags': previous.get('flags', 0),
        }
        for field in ('content', 'embeds', 'flags'):
            if field in payload:
                result[field] = payload[field] or ('' if field == 'content' else [])
        self.messages[key] = result
        self.last_payload = payload
        return result

    async def response(self, interaction_id, token, *, params, **kwargs):
        payload = params.payload
        data = payload.get('data') or {}
        msg = self.message(data, token)
        if payload['type'] == 5:
            self.deferred_tokens.add(token)
        callback = {'interaction': {'id': str(interaction_id), 'response_message_id': msg['id']}}
        if payload['type'] in (4, 7):
            callback['resource'] = {'type': payload['type'], 'message': msg}
        return callback

    async def followup(self, application_id, token, *, payload, **kwargs):
        if token in self.deferred_tokens:
            self.deferred_tokens.remove(token)
            key = token
        else:
            key = (token, self.counter)
        return self.message(payload, key)

    async def edit_original(self, application_id, token, *, payload, **kwargs):
        return self.message(payload, token)

    async def edit_webhook(self, application_id, token, message_id, *, payload, **kwargs):
        key = next(key for key, value in self.messages.items() if value['id'] == str(message_id))
        return self.message(payload, key)

    async def test_response_flags_return_value_and_embed_image(self):
        press = self.interaction()
        embed = discord.Embed(title='Profile').set_image(url='https://example.com/card.png')
        result = await press.response.send_message('Your profile', embed=embed, ephemeral=True, silent=True)
        self.assertIsInstance(result, discord.InteractionCallbackResponse)
        self.assertEqual(self.last_payload['content'], 'Your profile')
        self.assertEqual(self.last_payload['flags'] & 64, 64)
        self.assertEqual(self.last_payload['flags'] & 4096, 4096)
        self.assertEqual(self.last_payload['embeds'][0]['image']['url'], 'https://example.com/card.png')
        self.assertEqual(len(self.last_payload['embeds']), 2)
        await press.edit_original_response(content='Updated')
        self.assertNotIn('embeds', self.last_payload)
        self.assertEqual(self.last_payload['content'], 'Updated')

    async def test_defer_card_edit_keeps_ephemeral_without_extra_requests(self):
        press = self.interaction()
        await press.response.defer(ephemeral=True)
        card = discord.File(io.BytesIO(b'fake-test-image'), filename='profile.png')
        # A file produces multipart data, so capture before the real serializer
        # and let its successful path parse a valid response.
        async def multipart_edit(application_id, token, **kwargs):
            import json
            self.assertEqual(kwargs['files'], [card])
            payload = kwargs['payload']
            if payload is None:
                payload = json.loads(next(part['value'] for part in kwargs['multipart'] if part['name'] == 'payload_json'))
            return self.message(payload, token)
        self.adapter.edit_original_interaction_response.side_effect = multipart_edit
        result = await press.edit_original_response(attachments=[card], view=discord.ui.View())
        self.assertIsInstance(result, discord.InteractionMessage)
        self.assertEqual(result.flags.ephemeral, True)
        self.assertEqual(len(self.last_payload['embeds']), 1)
        self.assertEqual(self.adapter.create_interaction_response.await_count, 1)
        self.assertEqual(self.adapter.edit_original_interaction_response.await_count, 1)

    async def test_followup_and_original_edit_do_not_duplicate(self):
        press = self.interaction()
        await press.response.defer(ephemeral=True)
        result = await press.followup.send('Result', ephemeral=True)
        self.assertIsInstance(result, discord.WebhookMessage)
        self.assertEqual(len(self.last_payload['embeds']), 1)
        await press.edit_original_response(content='Revised result')
        self.assertNotIn('embeds', self.last_payload)
        self.assertEqual(self.last_payload['content'], 'Revised result')
        await result.edit(content='Another revision')
        self.assertNotIn('embeds', self.last_payload)
        self.assertEqual(self.last_payload['content'], 'Another revision')

    async def test_component_edit_and_view_only_cleanup(self):
        press = self.interaction()
        await press.response.send_message(embed=discord.Embed(title='Page 1'))
        component = self.interaction(token='component-token', type=3, message=self.messages[press.token])
        await component.response.edit_message(embed=discord.Embed(title='Page 2'))
        self.assertEqual(len(self.last_payload['embeds']), 2)
        await component.edit_original_response(view=None)
        self.assertNotIn('embeds', self.last_payload)
        self.assertNotIn('content', self.last_payload)

    async def test_layout_view_and_subsequent_omitted_view_edit_untouched(self):
        press = self.interaction()
        view = discord.ui.LayoutView()
        view.add_item(discord.ui.TextDisplay('Components v2 card'))
        await press.response.send_message(view=view)
        self.assertNotIn('embeds', self.last_payload)
        self.assertFalse(self.last_payload.get('content'))
        await press.edit_original_response(attachments=[])
        self.assertNotIn('embeds', self.last_payload)
        self.assertNotIn('content', self.last_payload)

    async def test_other_clients_and_incoming_webhooks_untouched(self):
        other = discord.Client(intents=discord.Intents.none())
        try:
            press = self.interaction()
            press._client = other
            await press.response.send_message('Other bot')
            self.assertNotIn('embeds', self.last_payload)
            hook = discord.Webhook.from_state(
                data={'id': '44444444', 'type': 1, 'token': 'test-incoming-token'}, state=self.state)
            await hook.send('Background event')
            self.assertNotIn('embeds', self.last_payload)
        finally:
            await other.close()

    async def test_idempotent_install_and_clean_uninstall(self):
        wrapped = discord.InteractionResponse.send_message
        self.hooks.install()
        self.assertIs(discord.InteractionResponse.send_message, wrapped)
        self.hooks.uninstall()
        self.assertIsNot(discord.InteractionResponse.send_message, wrapped)
        press = self.interaction()
        await press.response.send_message('After unload')
        self.assertNotIn('embeds', self.last_payload)

    async def test_followup_edit_keyword_id_and_cache_eviction(self):
        press = self.interaction()
        await press.response.defer()
        result = await press.followup.send('Result')
        await press.followup.edit_message(message_id=result.id, embed=discord.Embed(title='New card'))
        self.assertEqual(len(self.last_payload['embeds']), 2)
        self.hooks._modes.clear()
        await result.edit(content='Text after cache eviction')
        self.assertEqual(self.last_payload['content'], 'Text after cache eviction')
        self.assertNotIn('embeds', self.last_payload)
        self.assertEqual(len(self.messages[press.token]['embeds']), 2)

    async def test_missing_guild_embed_permission_survives_defer_and_followup(self):
        press = self.interaction()
        press.guild_id = 1234
        press._app_permissions = discord.Permissions(send_messages=True).value
        await press.response.defer(ephemeral=True)
        await press.followup.send('Result', ephemeral=True)
        self.assertNotIn('embeds', self.last_payload)
        self.assertIn(fundraiser.CONTENT_NOTICE, self.last_payload['content'])
        await press.edit_original_response(content='Updated result')
        self.assertNotIn('embeds', self.last_payload)
        self.assertEqual(self.last_payload['content'].count(fundraiser.CONTENT_NOTICE), 1)

    async def test_channel_ui_payload_uses_same_notice_and_permissions(self):
        channel = SimpleNamespace(guild=None)
        payload = self.hooks.for_ui({'embed': discord.Embed(title='Rank refresh')}, channel)
        self.assertEqual(len(payload['embeds']), 2)
        channel.guild = SimpleNamespace(me=object())
        channel.permissions_for = lambda member: discord.Permissions(send_messages=True)
        payload = self.hooks.for_ui({'content': 'Rank refresh'}, channel)
        self.assertNotIn('embeds', payload)
        self.assertIn(fundraiser.CONTENT_NOTICE, payload['content'])

    async def test_failed_send_keeps_original_error_and_does_not_retry(self):
        self.adapter.create_interaction_response.side_effect = RuntimeError('Simulated transport failure')
        press = self.interaction()
        with self.assertRaisesRegex(RuntimeError, 'Simulated transport failure'):
            await press.response.send_message('Result')
        self.assertEqual(self.adapter.create_interaction_response.await_count, 1)
        self.assertEqual(self.hooks._get(self.hooks._original_key(press)), 'unknown')

    async def test_second_followup_does_not_change_original_notice_mode(self):
        press = self.interaction()
        await press.response.defer()
        first = await press.followup.send('Original')
        second = await press.followup.send('Extra', embeds=[discord.Embed(description='x')] * 10)
        self.assertNotEqual(first.id, second.id)
        self.assertIn(fundraiser.CONTENT_NOTICE, second.content)
        self.assertEqual(self.hooks._get(self.hooks._original_key(press)), 'embed')
        await press.edit_original_response(content='Updated original')
        self.assertEqual(self.last_payload['content'], 'Updated original')
        self.assertNotIn('embeds', self.last_payload)
        await second.edit(content='Updated extra')
        self.assertIn(fundraiser.CONTENT_NOTICE, self.last_payload['content'])

    async def test_stale_message_uses_latest_mode_and_background_messages_untouched(self):
        press = self.interaction()
        await press.response.send_message(embed=discord.Embed(title='Card'))
        message = discord.Message(state=self.state, channel=press.channel, data=self.messages[press.token])
        async def edit(channel_id, message_id, *, params):
            return self.message(params.payload, press.token)
        self.state.http.edit_message = AsyncMock(side_effect=edit)
        await message.edit(content='Result', embeds=[discord.Embed(description='x')] * 10)
        self.assertIn(fundraiser.CONTENT_NOTICE, self.last_payload['content'])
        # The UI retains the old Message object, as MessageUI._redraw does.
        await message.edit(content='Updated result')
        self.assertIn(fundraiser.CONTENT_NOTICE, self.last_payload['content'])
        background_data = self.message({'content': 'Scheduled update'}, 'background')
        background = discord.Message(state=self.state, channel=press.channel, data=background_data)
        await background.edit(content='Scheduled update changed')
        self.assertEqual(self.last_payload['content'], 'Scheduled update changed')
        self.assertNotIn('embeds', self.last_payload)


if __name__ == '__main__':
    unittest.main(verbosity=2)
