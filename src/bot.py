#!/usr/bin/env python
##
# generic slack bot class
# largely based on Gendo but with some more bells and whistles
# (https://github.com/nficano/gendo)
#
# triggers:
#   - match exact phrase
#   - listen for phrase anywhere in message
#   - match command and regex pattern arguments
#
# options:
#   - verify sending user is on admin list
#
# custom variables and commands:
#   - replace variables in Slack message
#       - {user.name} : users name as string
#   - upload file to Slack and add comment
#       - {upload} : upload data in this message
#       - {comment.start:"String here":comment.end} : User "String here" as upload comment message
#
# https://github.com/deadbits/fluffy-system
# author: adam m. swanda
##

import os
import re
import sys
import time
import threading

from slackclient import SlackClient


class SlackBot(object):
    def __init__(self, token, config={}, debug=True):
        self.name = '(slackbot)'
        self.debug = debug
        self.bot_name = config.get('username')
        self.client = SlackClient(token)
        self.admins = {user: None for user in config.get('admins')} if config.get('admins') else {}
        self.users = {}
        self.listeners = []
        self.running = False


    def command(self, phrase, **options):
        def decorator(func):
            def wrapped(*args):
                if self._verify((options)):
                    self.add_listener('command', phrase, func, args, options)
                return func
            return wrapped()
        return decorator


    def listen(self, phrase, **options):
        def decorator(func):
            def wrapped(*args):
                self.add_listener('listen', phrase, func, args, options)
                return func
            return wrapped()
        return decorator


    def exact(self, phrase, **options):
        def decorator(func):
            def wrapped(*args):
                self.add_listener('exact', phrase, func, args, options)
                return func
            return wrapped()
        return decorator


    def _run_wrapped(self, func, user_id, message, *func_args):
        """Safely run wrapped functions."""
        try:
            response = func(user_id, message, *func_args)
            return response
        except Exception as err:
            return "I'm sorry Dave, I'm afraid I can't do that. (%s)" % str(err)


    def _verify(self, options):
        """Ensure command rules have appropriate keyword arguments."""
        if not options.get('match'):
            raise ValueError('command triggers must include the "match" option')
        if not isinstance(options.get('match'), re._pattern_type):
            raise AttributeError('match decorator keyword must be a regex pattern type')
        return True


    def _debug(self, message):
        """Print debug messages for basically everything."""
        if self.debug:
            print message


    def _keepalive(self):
        self._debug('(debug) started keep alive thread')
        while True:
            time.sleep(1800)
            self.client.server.ping()
            if not self.running:
                break


    def add_listener(self, rule, phrase, func=None, f_args=None, options=None):
        """Add new rule listeners."""
        self.listeners.append((rule, phrase, func, f_args, options))


    def run(self):
        """Read rtm connection for messages and send to handler."""
        self.running = True
        if self.client.rtm_connect():
            self._debug('(debug) started rtm connection')
            threading.Thread(target=self._keepalive, args=()).start()
            self.populate_user_mappings()
            while self.running:
                time.sleep(0.5)
                try:
                    data = self.client.rtm_read()
                    if data and data[0].get('type') == 'message':
                        user_id = data[0].get('user')
                        if self.get_user_name(user_id) == self.bot_name:
                            pass
                        else:
                            message = data[0].get('text')
                            channel = data[0].get('channel')
                            self.handle_message(user_id, message, channel)
                except (KeyboardInterrupt, SystemExit):
                    self.running = False
        else:
            print 'error: failed to initialize RTM connection to Slack\npossible invalid API token or network issues?'
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)


    def handle_message(self, user_id, message, channel):
        """Attempt to respond to received messages."""
        if not message:
            return

        self._debug('(debug) handled stripped message %s' % message.strip())
        for rule, phrase, func, func_args, decorator_opts in self.listeners:
            cmd_buff = phrase + ' '

            if rule == 'command' and message.lower().startswith(cmd_buff) and not message.lower().strip() == phrase:
                self._debug('(debug) responding to command event `%s`' % message)
                supplied_args = message.split(cmd_buff)[1].lstrip()
                re_match = decorator_opts.get('match').match(supplied_args.strip())
                if re_match:
                    func_args = re_match.groups()
                self.start_thread(func, func_args, decorator_opts, user_id, message, channel)

            if rule == 'listen' and phrase in message.lower():
                self._debug('(debug) responding to listen event `%s`' % message)
                self.start_thread(func, func_args, decorator_opts, user_id, message, channel)

            if rule == 'exact' and phrase == message.strip():
                self._debug('(debug) responding to message event `%s`' % message)
                self.start_thread(func, func_args, decorator_opts, user_id, message, channel)

            else:
                pass


    def start_thread(self, func, func_args, decorator_opts, user_id, message, channel):
        """Create a thread for validated messages bot is responding to."""
        thread = threading.Thread(target=self.respond, args=(func, func_args, decorator_opts, user_id, message, channel))
        thread.setDaemon(True)
        thread.start()


    def respond(self, func, func_args, decorator_opts, user_id, message, channel):
        upload = False

        if decorator_opts.get('admin_only'):
            if not self.is_admin(user_id):
                response = 'sorry {user.name}, only bot admins can run this command.'
            else:
                response = self._run_wrapped(func, user_id, message, *func_args)
        else:
            response = self._run_wrapped(func, user_id, message, *func_args)

        if response:

            if '{upload}' in response:
                self._debug('(debug) parsing {upload} command')
                response, comment = self.parse_upload_command(response)
                upload = True

            if '{user.name}' in response:
                self._debug('(debug) replacing {user.name} in response %s' % response)
                response = response.replace('{user.name}', self.get_user_name(user_id))

            if decorator_opts.get('target_channel'):
                self._debug('(debug) setting target channel from decorator option')
                channel = self.get_channel_by_name(decorator_opts.get('target_channel'))

            elif decorator_opts.get('target_user'):
                self._debug('(debug) setting target user from decorator option')
                target_user = decorator_opts.get('target_user')
                channel = self.get_user_direct_channel(self.get_user_by_name(target_user))

            if upload:
                self.upload_file(response, channel, comment)
            else:
                self.send_message(response, channel)


    def parse_upload_command(self, response):
        comment = None
        response = response.replace('{upload}', '').strip()
        re_comment = re.compile(r'({comment\.start:"(.*)":comment\.end})').match(response)
        if re_comment:
            if len(re_comment.groups()) == 2:
                comment = re_comment.groups()[1]
                response = response.replace('{comment.start:"%s":comment.end}' % comment, '').strip()
        return (response, comment)


    def send_message(self, message, channel):
        """Send message to channel."""
        #self._debug('(debug) send_message(%s, %s) -- api call: chat.postMessage' % (message, channel))
        self.client.api_call('chat.postMessage', as_user='true:', channel=channel, text=message)


    def upload_file(self, file_data, channel, file_comment=None):
        comment = file_comment if file_comment is not None else ''
        self.client.api_call('files.upload', channels=channel, content=file_data, initial_comment=comment)


    def get_user_info(self, user_id):
        """Return all info for a user by id."""
        self._debug('(debug) get_user_info(%s) -- api call: users.info' % user_id)
        return self.client.api_call('users.info', user=user_id)


    def get_user_name(self, user_id):
        """Return user name by id from self.users or API call."""
        self._debug('(debug) get_user_name(%s)' % user_id)
        if user_id in self.users.values():
            return self.get_stored_username(user_id)
        else:
            user = self.get_user_info(user_id)
            user_name = user.get('user', {}).get('name')
            self.users[user_name] = user_id
        return user_name


    def get_user_by_name(self, user_name):
        """Return user id by name from self.users or API call."""
        self._debug('(debug) get_user_by_name(%s)' % user_name)
        if user_name in self.users.keys():
            return self.users[user_name]
        else:
            self._debug('(debug) get_user_by_name(%s) -- api call: users.list' % user_name)
            members = self.client.api_call('users.list')
            user_id = [member.get('id') for member in members.get('members') if member.get('name') == user_name]
            if user_id:
                self.users[user_name] = user_id[0]
                return user_id[0]
        return None


    def get_user_direct_channel(self, user_id):
        """Open direct channel with user by user id and return channel id."""
        self._debug('(debug) get_user_direct_channel(%s) -- api call: im.open' % user_id)
        channel = self.client.api_call('im.open', user=user_id)
        channel_id = channel.get('channel').get('id')
        return channel_id


    def get_channel_by_name(self, channel_name):
        """Return channel id by name."""
        self._debug('(debug) get_channel_by_name(%s)' % channel_name)
        channel_id = self.client.server.channels.find(channel_name).id
        return channel_id


    def get_stored_username(self, user_id):
        """Lookup username by ID from self.users dictionary."""
        for name, _id in self.users.items():
            if _id == user_id:
                return name


    def populate_user_mappings(self):
        """Store all available user name to id mappings for self.users and self.admins on self.run()."""
        self._debug('(debug) populate_user_mappings() -- api call: users.list')
        members = self.client.api_call('users.list')
        for member in members.get('members'):
            user_name = member.get('name')
            user_id = member.get('id')
            self.users[user_name] = user_id
            if user_name in self.admins.keys():
                self.admins[user_name] = user_id
        if self.bot_name is None:
            self.bot_name = self.client.server.login_data['self']['name']


    def is_admin(self, user_id):
        """Check if user is a bot admin by user id as defined in self.admins."""
        self._debug('(debug) is_admin(%s)' % user_id)
        if user_id in self.admins.values():
            return True
        else:
            user_name = self.get_user_name(user_id)
            if user_name in self.admins.keys():
                self.admins[user_name] = user_id
                return True
        return False
