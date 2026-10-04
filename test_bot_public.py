import ast
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, mock_open, patch


class DiscordChannelTests(unittest.TestCase):
  def setUp(self):
    self.tree = ast.parse(Path(__file__).with_name('bot-public.py').read_text())
    functions = {'prompt_channel_id', 'get_messages', 'get_messages_historic'}
    nodes = [
      node for node in self.tree.body
      if isinstance(node, ast.FunctionDef) and node.name in functions
      or isinstance(node, ast.Assign)
      and any(isinstance(target, ast.Name) and target.id == 'DISCORD_HEADERS'
              for target in node.targets)
    ]
    # Load the functions without running the top-level KML/scoring pipeline.
    self.requests = SimpleNamespace(get=Mock(), RequestException=OSError)
    self.namespace = {
      'requests': self.requests,
      'json': json,
      'time': SimpleNamespace(sleep=Mock()),
      'start_users': ['starter'],
      'start_messages': ['round start'],
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'bot-public.py', 'exec'),
         self.namespace)

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

  def test_startup_selects_channel_before_fetching(self):
    nodes = self.tree.body
    start = next(i for i, node in enumerate(nodes)
                 if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == 'guild_id'
                         for target in node.targets))
    for mode in ('auto', 'historic'):
      with self.subTest(mode=mode):
        namespace = {
          'prompt_guild_id': Mock(return_value='123'),
          'prompt_channel_id': Mock(return_value='456'),
          'prompt_mode': Mock(return_value=mode),
          'get_messages': Mock(return_value=[]),
          'get_messages_historic': Mock(return_value=[]),
        }
        with patch('builtins.input', side_effect=['10', '20']):
          exec(compile(ast.Module(body=nodes[start:start + 4], type_ignores=[]),
                       'bot-public.py', 'exec'), namespace)
        namespace['prompt_channel_id'].assert_called_once_with('123')
        self.assertEqual(namespace['channel_id'], '456')
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
