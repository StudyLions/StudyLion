
## StudyLion - Discord Study & Productivity Bot

StudyLion is a Discord bot that tracks members' study and work time while offering members the ability to view their statistics and use productivity tools such as: To-do lists, pomodoro timers, reminders, and much more.

  

[**Invite StudyLion here**](https://discord.studylions.com/invite "here"), and get started with `!help`.

Join the [**support server**](https://discord.gg/studylions "support server") to contact us if you need help configuring the bot on your server, or start a [**discussion**](https://github.com/StudyLions/StudyLion/discussions "disscussion") to report issues and bugs.



### The Idea


In the past couple of years, we noticed a new trend on Discord – instead of being a platform designed only for gamers, many students joined it as well, forming communities dedicated to studying and working together.



This bot was founder by [Ari Horesh](https://www.youtube.com/arihoresh) (Ari Horesh#0001) to support these forming study communities and allow students all over the world to study better.

### Self Hosting

We offer private instances based on availablity (a private bot for your community) to server owners who want their own branding (logo, color scheme, private and seperate database, better response-rate, and customizability to the text itself). 
If you are intrested, contact the founder at contact@arihoresh.com . 

You can self-host and fork the bot using the following steps, but beware that this version **does not include** our visual graphical user interface, which is only include in the custom private instances or our the public instance.

Follow the steps below to self-host the bot.
- Clone the repo recursively (which makes sure to include the cmdClient submodule, otherwise you need to initialise it separately) 
-  Install the requirements from `requirements.txt` 
- Install Postgresql, and setup a database with the schema given in `data/schema.sql` 
-  Copy `config/example-bot.conf` to `config/bot.conf`, filling in the appropriate information, including database connection arguments. 
- Start the bot from the top level `run.py`.

We do not offer support for self-hosted bots, the code is provided as is without warranty of any kind. 

## Features


- **Students Cards and Statistics**

Allow users to create their own private student profile cards and set customs study field tags by using `!stats` and `!setprofile`

![Discord Study Bot Profile Card](https://i.imgur.com/dEZvawb.png)

- **Camera only study rooms**

Set specific channels to force users to use their webcam to study.

![discord study rooms](https://i.imgur.com/rlsH8a6.png)

- **To-Do List**

Users can create and share their own to-do lists, and get rewards when completing a task! Use `!todo` to launch our interactive to do list!

- **Reminders**

Users can set their own private reminders, to drink water, stretch, or anything else they want to remember, every X minutes, hours, days, or maybe even just once. 

Example: `!remindme to drink water every 3h` will send you a reminder every 3 hours to drink water. 

![discord bot to do lists and reminders](https://i.imgur.com/BMFK2gJ.png)

- **Scheduled Sessions**

This feature allows the users to use their coins to schedule a time to study at. Book rooms using `!rooms book`

Not attending prevents everyone in the room from getting the bonus.

![scheuduled study rooms discord](https://i.imgur.com/6dMSqDh.png)

- **Study and Work Statistics**

In addition to the profile cards, users can view their daily, weekly, monthly and all-time stats, as well as their study streak. Use `!weekly` and `!monthly` to view your revision statistics in more detail.

![weekly and monthly statistics discord study](https://i.imgur.com/i7JutEh.png)

- **Pomodoro Timers**

The bot will show the timer in the title of the study room and play a sound at the start and end of each session. 
Commands:  `!timer` , `!pomodoro`

![Pomodoro timer Discord](https://i.imgur.com/UcNXpv3.png)

- **Private Study Rooms**

Allows the members to create their own private study rooms and invite their friends to join! 
Rent a room using `!rent [usernames]`. 

- **Workout Rooms**

Allows the Admins to create workout rooms with a bonus for people who workout.

- **Study Tiers and Achievements**

Reward users based on their total study time, allow them to get better ranks, and show off how long they've been working.


- **Full-Scale Economy System**

Reward users for studying, allow them to use the coins to buy private study rooms, schedule accountability rooms, and even change their name's color.

- **Full-Scale Moderation System**

Punish cheaters, audit-log, welcome message, and so much more using our full-scale moderation system.

## Tutorials

A command list and general documentation for StudyLion may be found using the `!help` command, and documentation for a specific command, e.g. `config`, may be found with `!help config`.

Make sure to check the [full documentation](https://www.notion.so/izabellakis/StudyLion-Bot-Tutorials-f493268fcd12436c9674afef2e151707 "StudyLion Tutorial") to stay updated.

## Developers/Contributors/Project Watchers

You can follow the Project's Kanban board (for planned features, what the team is currently working on, bug/issue-traker, ideas, etc..) on Trello [here](https://trello.com/b/0zOxkqyO/studylion-bot-dev).

<br>
<a href="https://imgur.com/ziPdJGw"><img src="https://i.imgur.com/ziPdJGws.png" title="source: imgur.com" /></a>
