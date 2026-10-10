import ast
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from urllib.parse import quote
from unittest.mock import Mock, mock_open, patch


class DiscordChannelTests(unittest.TestCase):
  def setUp(self):
    self.tree = ast.parse(Path(__file__).with_name('bot-public.py').read_text())
    functions = {
      'test_discord_auth', 'troubleshoot_thread_access', 'prompt_channel_id',
      'prompt_mode', 'get_messages',
      'get_messages_historic', 'get_message_reactions',
    }
    nodes = [
      node for node in self.tree.body
      if isinstance(node, ast.FunctionDef) and node.name in functions
      or isinstance(node, ast.Assign)
      and any(isinstance(target, ast.Name)
              and target.id in {'DISCORD_TOKEN', 'DISCORD_HEADERS'}
              for target in node.targets)
    ]
    # Load the functions without running the top-level KML/scoring pipeline.
    self.requests = SimpleNamespace(get=Mock(), RequestException=OSError)
    self.namespace = {
      'requests': self.requests,
      'json': json,
      'os': os,
      'time': SimpleNamespace(sleep=Mock()),
      'quote': quote,
      'start_users': ['starter'],
      'start_messages': ['round start'],
    }
    with patch.dict(os.environ, {'DISCORD_TOKEN': 'test-token'}):
      exec(compile(ast.Module(body=nodes, type_ignores=[]), 'bot-public.py', 'exec'),
           self.namespace)

  def test_discord_auth_succeeds(self):
    response = Mock(
      status_code=200, ok=True,
      json=Mock(return_value={'username': 'test-bot', 'id': '123'}))
    self.requests.get.return_value = response

    with patch('builtins.print'):
      self.assertTrue(self.namespace['test_discord_auth']())

    self.requests.get.assert_called_once_with(
      'https://discord.com/api/v10/users/@me',
      headers=self.namespace['DISCORD_HEADERS'], timeout=30)

  def test_discord_auth_fails_without_token(self):
    self.namespace['DISCORD_TOKEN'] = ''

    with patch('builtins.print'):
      self.assertFalse(self.namespace['test_discord_auth']())

    self.requests.get.assert_not_called()

  def test_discord_auth_fails_on_request_error(self):
    self.requests.get.side_effect = OSError('Connection failed')

    with patch('builtins.print'):
      self.assertFalse(self.namespace['test_discord_auth']())

  def test_discord_auth_fails_on_rejected_credentials(self):
    self.requests.get.return_value = Mock(
      status_code=401, ok=False, text='Unauthorized')

    with patch('builtins.print'):
      self.assertFalse(self.namespace['test_discord_auth']())

  def test_discord_auth_fails_on_malformed_json(self):
    self.requests.get.return_value = Mock(
      status_code=200, ok=True,
      json=Mock(side_effect=ValueError('Invalid JSON')))

    with patch('builtins.print'):
      self.assertFalse(self.namespace['test_discord_auth']())

  def response(self, guild_id):
    return Mock(json=Mock(return_value={'guild_id': guild_id}))

  def test_select_channel_and_retry_invalid_input(self):
    self.requests.get.return_value = self.response('123')
    with patch('builtins.input', side_effect=['', 'abc', '１２３', ' 456 ']), \
         patch('builtins.print'):
      channel_id = self.namespace['prompt_channel_id']('123')
    self.assertEqual(channel_id, '456')
    self.requests.get.assert_called_once_with(
      'https://discord.com/api/v10/channels/456',
      headers=self.namespace['DISCORD_HEADERS'], timeout=30)
    self.requests.get.return_value.raise_for_status.assert_called_once()

  def test_reject_channel_from_another_server_or_dm(self):
    self.requests.get.side_effect = [
      self.response('999'), self.response(None), self.response('123')]
    with patch('builtins.input', side_effect=['111', '222', '456']), \
         patch('builtins.print'):
      self.assertEqual(self.namespace['prompt_channel_id']('123'), '456')
    self.assertEqual(self.requests.get.call_count, 3)

  def test_select_thread_with_server_id(self):
    for thread_type in (10, 11, 12):
      with self.subTest(thread_type=thread_type):
        self.requests.get.reset_mock()
        self.requests.get.return_value = Mock(json=Mock(return_value={
          'guild_id': '123', 'type': thread_type, 'parent_id': '789'}))
        with patch('builtins.input', return_value='456'):
          self.assertEqual(self.namespace['prompt_channel_id']('123'), '456')
        self.requests.get.assert_called_once_with(
          'https://discord.com/api/v10/channels/456',
          headers=self.namespace['DISCORD_HEADERS'], timeout=30)

  def test_select_thread_using_parent_server(self):
    for thread_type in (10, 11, 12):
      with self.subTest(thread_type=thread_type):
        self.requests.get.reset_mock()
        self.requests.get.side_effect = [
          Mock(json=Mock(return_value={'type': thread_type, 'parent_id': '789'})),
          self.response('123')]
        with patch('builtins.input', return_value='456'):
          self.assertEqual(self.namespace['prompt_channel_id']('123'), '456')
        self.assertEqual(self.requests.get.call_args_list[0].args[0],
                         'https://discord.com/api/v10/channels/456')
        self.assertEqual(self.requests.get.call_args_list[1].args[0],
                         'https://discord.com/api/v10/channels/789')
        self.assertEqual(self.requests.get.call_args.kwargs,
                         {'headers': self.namespace['DISCORD_HEADERS'], 'timeout': 30})

  def test_reject_thread_from_another_server(self):
    self.requests.get.side_effect = [
      Mock(json=Mock(return_value={'type': 11, 'parent_id': '789'})),
      self.response('999'), self.response('123')]
    with patch('builtins.input', side_effect=['111', '456']), \
         patch('builtins.print') as output:
      self.assertEqual(self.namespace['prompt_channel_id']('123'), '456')
    output.assert_called_once_with(
      "Channel does not belong to the selected server. Please try again.")

  def test_access_errors_explain_thread_requirements(self):
    for status, guidance in [(401, 'DISCORD_TOKEN'), (403, 'Private threads'),
                             (404, 'channel or thread ID')]:
      for parent_lookup in (False, True):
        with self.subTest(status=status, parent_lookup=parent_lookup):
          failure = Mock(status_code=status)
          failure.raise_for_status.side_effect = OSError('Access denied')
          responses = [failure, self.response('123')]
          if parent_lookup:
            responses.insert(0, Mock(json=Mock(return_value={
              'type': 12, 'parent_id': '789'})))
          self.requests.get.side_effect = responses
          inputs = ['111', '456']
          if status == 403 and not parent_lookup:
            inputs.insert(1, '')
          with patch('builtins.input', side_effect=inputs), \
               patch('builtins.print') as output:
            self.assertEqual(self.namespace['prompt_channel_id']('123'), '456')
          message = '\n'.join(call.args[0] for call in output.call_args_list)
          self.assertIn(f'HTTP {status}', message)
          self.assertIn(guidance, message)
          if status == 401:
            self.assertNotIn('DISCORD_HEADERS', message)

  def test_forbidden_thread_can_probe_parent_and_retry(self):
    failure = Mock(status_code=403, json=Mock(return_value={
      'code': 50001, 'message': 'Missing Access'}))
    failure.raise_for_status.side_effect = OSError('Forbidden')
    self.requests.get.side_effect = [
      failure, self.response('123'), self.response('123')]
    with patch('builtins.input', side_effect=['111', '789', '456']), \
         patch('builtins.print') as output:
      self.assertEqual(self.namespace['prompt_channel_id']('123'), '456')
    message = '\n'.join(call.args[0] for call in output.call_args_list)
    self.assertIn('50001 (Missing Access)', message)
    self.assertIn('not your personal Discord account', message)
    self.assertIn('role and member overrides', message)
    self.assertIn('The bot can retrieve this parent channel', message)
    self.requests.get.assert_any_call(
      'https://discord.com/api/v10/channels/789',
      headers=self.namespace['DISCORD_HEADERS'], timeout=30)

  def test_parent_probe_reports_errors_and_wrong_server(self):
    forbidden = Mock(status_code=403)
    forbidden.raise_for_status.side_effect = OSError('Forbidden')
    cases = [
      (forbidden, 'Parent access check failed'),
      (OSError('Connection failed'), 'Parent access check failed'),
      (Mock(status_code=200, json=Mock(side_effect=ValueError('Invalid JSON'))),
       'Parent access check failed'),
      (self.response('999'), 'does not belong to the selected server'),
      (Mock(json=Mock(return_value={'guild_id': '123', 'type': 11})),
       'That ID is another thread'),
    ]
    for response, expected in cases:
      with self.subTest(expected=expected):
        self.requests.get.side_effect = [response]
        with patch('builtins.input', return_value='789'), \
             patch('builtins.print') as output:
          self.namespace['troubleshoot_thread_access'](
            Mock(json=Mock(return_value={'code': 50013})), '123')
        message = '\n'.join(call.args[0] for call in output.call_args_list)
        self.assertIn('50013 (Missing Permissions)', message)
        self.assertIn(expected, message)

  def test_diagnostics_skip_invalid_parent_and_malformed_error(self):
    for parent_id in ('', 'abc', '１２３'):
      for error in (ValueError('Invalid JSON'), ['not an error object']):
        with self.subTest(parent_id=parent_id, error=error):
          self.requests.get.reset_mock()
          response = Mock()
          if isinstance(error, ValueError):
            response.json.side_effect = error
          else:
            response.json.return_value = error
          with patch('builtins.input', return_value=parent_id), \
               patch('builtins.print'):
            self.namespace['troubleshoot_thread_access'](response, '123')
          self.requests.get.assert_not_called()

  def test_failed_known_parent_does_not_prompt_or_probe_again(self):
    with patch('builtins.input') as prompt, patch('builtins.print') as output:
      self.namespace['troubleshoot_thread_access'](
        Mock(json=Mock(return_value={})), '123', '789')
    prompt.assert_not_called()
    self.requests.get.assert_not_called()
    self.assertIn('parent channel 789, not the thread', output.call_args.args[0])

  def test_retry_parent_connection_error_without_stale_status(self):
    self.requests.get.side_effect = [
      Mock(status_code=200, json=Mock(return_value={'type': 11, 'parent_id': '789'})),
      OSError('Connection failed'), self.response('123')]
    with patch('builtins.input', side_effect=['111', '456']), \
         patch('builtins.print') as output:
      self.assertEqual(self.namespace['prompt_channel_id']('123'), '456')
    self.assertNotIn('HTTP 200', output.call_args.args[0])

  def test_retry_api_and_json_errors(self):
    forbidden = self.response('123')
    forbidden.raise_for_status.side_effect = OSError('Forbidden')
    invalid_json = Mock()
    invalid_json.json.side_effect = ValueError('Invalid JSON')
    self.requests.get.side_effect = [
      OSError('Connection failed'), forbidden, invalid_json, self.response('123')]
    with patch('builtins.input', side_effect=['111', '222', '333', '456']), \
         patch('builtins.print'):
      self.assertEqual(self.namespace['prompt_channel_id']('123'), '456')

  def test_both_modes_fetch_selected_channel(self):
    self.namespace['channel_id'] = '456'
    submission = {'id': '20', 'author': {'username': 'player'}, 'content': 'photo'}
    start = {'id': '10', 'author': {'username': 'starter'}, 'content': 'round start'}
    for function, args in [('get_messages', ()), ('get_messages_historic', ('10', '20'))]:
      with self.subTest(mode=function):
        self.requests.get.reset_mock()
        self.requests.get.side_effect = None
        self.requests.get.return_value = Mock(
          status_code=200, text=json.dumps([submission, start]))
        with patch('builtins.open', mock_open()), patch('builtins.print'):
          self.assertEqual(self.namespace[function](*args), [submission])
        self.assertEqual(self.requests.get.call_args.args[0],
                         'https://discord.com/api/v10/channels/456/messages')
        self.assertEqual(self.requests.get.call_args.kwargs['headers'],
                         self.namespace['DISCORD_HEADERS'])

  def test_prompt_mode_accepts_reactions(self):
    with patch('builtins.input', side_effect=['REactions']), \
         patch('builtins.print'):
      self.assertEqual(self.namespace['prompt_mode'](), 'reactions')

  def test_get_message_reactions_lists_all_users_and_paginates(self):
    self.namespace['channel_id'] = '456'
    first_page = [{'id': str(i), 'username': f'user{i}'} for i in range(100)]
    second_page = [{'id': '100', 'username': 'user100'}]
    message = {'reactions': [
      {'emoji': {'name': 'thumbs up', 'id': None}},
      {'emoji': {'name': 'custom', 'id': '789'}},
    ]}
    self.requests.get.side_effect = [
      Mock(json=Mock(return_value=message)),
      Mock(json=Mock(return_value=first_page)),
      Mock(json=Mock(return_value=second_page)),
      Mock(json=Mock(return_value=[
        {'id': '1', 'username': 'user1'},
        {'id': '101', 'username': 'burst-user'},
      ])),
      Mock(json=Mock(return_value=[{'id': '101', 'username': 'custom-user'}])),
      Mock(json=Mock(return_value=[])),
    ]

    reactions = self.namespace['get_message_reactions']('123')

    self.assertEqual(reactions, [
      ('thumbs up', [f'user{i}' for i in range(100)] +
       ['user100', 'burst-user']),
      ('custom', ['custom-user']),
    ])
    reaction_calls = self.requests.get.call_args_list[1:]
    self.assertEqual(
        reaction_calls[0].args[0],
        'https://discord.com/api/v10/channels/456/messages/123/'
        'reactions/thumbs%20up')
    self.assertEqual(reaction_calls[1].kwargs['params'],
                    {'limit': 100, 'type': 0, 'after': '99'})
    self.assertEqual(reaction_calls[2].kwargs['params'], {'limit': 100, 'type': 1})
    self.assertEqual(
        reaction_calls[3].args[0],
        'https://discord.com/api/v10/channels/456/messages/123/'
        'reactions/custom%3A789')
    self.assertEqual(reaction_calls[4].kwargs['params'],
                    {'limit': 100, 'type': 1})

  def test_startup_stops_when_discord_authentication_fails(self):
    gate = next(node for node in self.tree.body
                if isinstance(node, ast.If)
                and isinstance(node.test, ast.UnaryOp)
                and isinstance(node.test.op, ast.Not)
                and isinstance(node.test.operand, ast.Call)
                and isinstance(node.test.operand.func, ast.Name)
                and node.test.operand.func.id == 'test_discord_auth')
    auth = Mock(return_value=False)
    namespace = {'test_discord_auth': auth}

    with patch('builtins.print'):
      with self.assertRaises(SystemExit) as exit_error:
        exec(compile(ast.Module(body=[gate], type_ignores=[]),
                     'bot-public.py', 'exec'), namespace)

    self.assertEqual(exit_error.exception.code, 1)
    auth.assert_called_once_with()

  def test_startup_selects_channel_before_fetching(self):
    nodes = self.tree.body
    start = next(i for i, node in enumerate(nodes)
                 if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == 'guild_id'
                         for target in node.targets))
    for mode in ('auto', 'historic', 'reactions'):
      with self.subTest(mode=mode):
        namespace = {
          'prompt_guild_id': Mock(return_value='123'),
          'prompt_channel_id': Mock(return_value='456'),
          'prompt_mode': Mock(return_value=mode),
          'get_messages': Mock(return_value=[]),
          'get_messages_historic': Mock(return_value=[]),
          'get_message_reactions': Mock(return_value=[]),
        }
        with patch('builtins.input', side_effect=['10', '20']):
          if mode == 'reactions':
            with self.assertRaises(SystemExit):
              exec(compile(ast.Module(body=nodes[start:start + 5], type_ignores=[]),
                           'bot-public.py', 'exec'), namespace)
            namespace['get_message_reactions'].assert_called_once_with('10')
          else:
            exec(compile(ast.Module(body=nodes[start:start + 5], type_ignores=[]),
                         'bot-public.py', 'exec'), namespace)
        namespace['prompt_channel_id'].assert_called_once_with('123')
        self.assertEqual(namespace['channel_id'], '456')
        if mode != 'reactions':
          namespace['get_messages' if mode == 'auto' else
                    'get_messages_historic'].assert_called_once()

  def test_links_use_selected_server_and_channel(self):
    node = next(node for node in ast.walk(self.tree)
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.JoinedStr)
                and any(isinstance(target, ast.Name) and target.id == 'pic_link'
                        for target in node.targets))
    namespace = {'guild_id': '123', 'channel_id': '456', 'message': {'id': '20'}}
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'bot-public.py', 'exec'),
         namespace)
    self.assertEqual(namespace['pic_link'], 'https://discord.com/channels/123/456/20')


if __name__ == '__main__':
  unittest.main()
