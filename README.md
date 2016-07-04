# fluffy-system
Python library for a Slack bot.  
Github chose the repo name for me... don't laugh at me.

## Description
This is a Python library that allows you to build your own Slack bot with relatively little effort.  
The class is based on the Gendo project but includes some more bells and whistles.
(https://github.com/nficano/gendo)
  
To create a bot you need a Slack bot token and then simply import the class. The next section details how to create
commands. Once your commands are all set, just call `SlackBot.run()` and your bot will have a long and merry existence. 

## Triggers  
The class has three different means of listening for messages:
- exact
    - Message must exactly match the trigger string
- command
    - Message must match trigger string and accepts arguments via regex pattern matching
- listen
    - Trigger string can be contained anywhere in the message

To use these listeners, simply add the appropriate decorator to your command function.  
The decorator function *must* accept the arguments `user` and `message` as the first and second arguments, respectively.  

Anything returned from the decorated function will be sent back to the calling Slack channel or user. This should
*always* be a string or stuff will break.  


## Target Users and Channels
Command responses can be sent directly to a specific user or channel by using the decorator options `target_channel` and `target_user`.
  
```
@bot.exact('!help', target_channel="main")

@bot.exact('!annoy', target_user="someone you dont like")
```


## Trigger Examples
*exact*  
```
from bot import SlackBot
conf = {'username': 'my_bot'}
bot = SlackBot(token='my token', config=conf)

@bot.exact('!help')
def cmd_help(user, message):
    return '{user.name} sent the !help command.'
```

*command*
Any matching content from the message will be sent to the decorator function as additional arguments.  
Using regex match groups will send each group as it's own argument, as shown in the example below:
  
```
search_re = re.compile(r'(.*)\s(.*)')

@bot.command('!search', match=search_re)
def cmd_search(user, message, key, value):
    return 'attempting to search for %s:%s' % (key, value)
```

*listen*
```
@bot.listen('tacos')
def cmd_tacos(user, message):
    return 'I love tacos too!'
```

## User argument
The `user` argument will be the calling Slack users ID. The ID is *not* the user name but an unique identifier Slack
uses per user.
  
If you wish to include the calling users name in the response, place `{user.name}` in the returned string. The bot will replace this with the username.

## Message argument
The message argument is the raw message that the calling user sent to the bot.

## Access Control
By adding Slack usernames to the 'admins' list in the bot config, you can then enforce access control on specific
commands.  

When adding the trigger decorator, simply add the argument `admin_only=True` to the decorator options and this will
restrict that command to be only executed by admin users. If the Slack user is not an admin, the
decorator function will not get called, so you only need to add code to the function that should execute upon
successful authorization.

```
@bot.exact('!admin', admin_only=True)
def cmd_admin(user, message):
    return '{user.name} is a valid admin.'
```

## Uploading snippets
Like the `{user.name}`, bots can create Slack snippet by including the `{upload}` string in a returned command response.  
  
You can also add a comment to the snippet by including the following:  
`{comment.start:"your comment here":comment.end}`  

Any other data in the command response is assumed to be the snippet content.
  
In the example below, a snippet would be created with the content "helllooooo world!" and the comment "whatever".
```
return '{upload} {comment.start:"whatever":comment.end} helllooooo world!'
```
