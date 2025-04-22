# Discord Transmog Bot

A Discord bot that enables users to submit transmog themes for World of Warcraft, with an automated weekly selection of a theme to showcase. The bot allows users to interact with it easily and provides essential commands for managing submissions.

## Features

- **Submit a New Theme**: Users can submit their transmog themes using the command `!tmnew <theme>`.
- **Cron based Selection**: Depending on the cron settings, the bot randomly selects one theme and posts it in the designated channel.
- **View All Themes**: Users can view all submitted themes using the command `!tmall`.
- **User Submission Count**: Check how many themes each user has submitted with the command `!tmuser`.
- **Get notifications**: With the command `!tmnotify` or `tmnotifyoff` notifications can be toggled.
- **Toggle the output**: The commands `!tmon` and `!tmoff` you can toggle the output of themes into the channel.
- **Help Command**: Get a list of available commands using `!tmhelp`.

## Setup

To set up the bot, follow these steps:

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/yourusername/transmog-bot.git
   cd transmog-bot

2. **Create a .env file (adjust the values to your needs)**:
```bash
CHANNEL_ID=
BOT_TOKEN=
CRON_DAY_OF_WEEK=mon-sun
CRON_HOUR=0-23
CRON_MINUTE=0-59