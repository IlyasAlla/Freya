# 🛡️ Freya - Advanced Discord Moderation Bot

A comprehensive, feature-rich Discord moderation bot built with discord.py v2.0+. Keep your server safe with powerful moderation tools, anti-spam protection, voice management, and extensive logging capabilities.

[![Discord.py](https://img.shields.io/badge/discord.py-v2.3+-blue.svg)](https://github.com/Rapptz/discord.py)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## ✨ Features

### 🔨 **Moderation Commands**
- **Mute System** - Permanent and temporary mutes with auto-unmute
- **Ban System** - Permanent and temporary bans with auto-unban
- **Timeout** - Discord's native timeout feature (up to 28 days)
- **Kick** - Remove problematic users
- **Warnings** - Issue and track user warnings
- **Message Management** - Purge and clear messages with advanced filters

### 🤖 **Auto-Moderation**
- **Anti-Spam Detection** - Automatically detects and punishes spam
- **Mention Limiting** - Prevents mention spam
- **Invite Blocker** - Block Discord invite links
- **Link Filter** - Optional external link blocking
- **Auto-Punish** - Automatic warnings and mutes for repeat offenders

### 📊 **Logging & History**
- **Comprehensive Logs** - All moderation actions logged to dedicated channel
- **SQLite Database** - Persistent storage for warnings and mod history
- **Moderation History** - View complete user moderation records
- **Warning System** - Track and manage user warnings

### 🔊 **Voice Management**
- Move, kick, mute, unmute, deafen, and undeafen users in voice channels
- Full voice channel control for moderators

### 👥 **Role & User Management**
- Add and remove roles from users
- Set and reset nicknames
- Auto-assign roles on member join
- Detailed user information lookup

### 🎮 **Utility & Fun**
- **Custom Embeds** - Create beautiful embed messages
- **Announcements** - Professional server announcements
- **Polls** - Interactive polls with reactions
- **Avatar/Banner** - Display user avatars and banners
- **Fun Commands** - 8ball, coinflip, dice roll

### ⚙️ **Configuration**
- Easy setup wizard
- Configurable moderator and admin roles
- Customizable anti-spam settings
- JSON-based persistent configuration

## 📋 Command List

### Moderation
```
/mute          - Mute a user indefinitely
/tempmute      - Temporarily mute a user
/unmute        - Unmute a user
/timeout       - Timeout a user (Discord native)
/untimeout     - Remove timeout from user
/kick          - Kick a user from the server
/ban           - Ban a user permanently
/tempban       - Temporarily ban a user
/unban         - Unban a user
/warn          - Warn a user
/warns         - View user warnings
/clearwarns    - Clear user warnings
/modlog        - View moderation history
/purge         - Delete multiple messages
/clear         - Advanced message deletion with filters
/slowmode      - Set channel slowmode
/lockdown      - Lock/unlock a channel
/movemsg       - Move messages to another channel
/whois         - Detailed user information
```

### Voice Management
```
/voicemove     - Move user to voice channel
/voicekick     - Kick user from voice
/vcmute        - Mute user in voice channel
/vcunmute      - Unmute user in voice
/vcdeafen      - Deafen user in voice
/vcundeafen    - Undeafen user in voice
```

### Role & User Management
```
/addrole       - Add a role to a user
/removerole    - Remove a role from a user
/setnick       - Set user nickname
/resetnick     - Reset user nickname
```

### Utility & Info
```
/userinfo      - Get user information
/serverinfo    - Get server information
/avatar        - Display user's avatar
/banner        - Display user's banner
/roles         - List all server roles
/embed         - Create custom embeds
/announce      - Send announcements
/poll          - Create polls with reactions
/help          - Show all commands
```

### Fun Commands
```
/8ball         - Ask the magic 8-ball
/coinflip      - Flip a coin
/roll          - Roll dice
```

### Configuration
```
/setup         - Initial bot setup
/setautorole   - Set auto-assign role
/config        - View current configuration
```

## 🚀 Installation

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)
- A Discord Bot Token

### Step 1: Clone the Repository
```bash
git clone https://github.com/IlyasAlla/Freya.git
cd Freya
```

### Step 2: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 3: Configure the Bot

**Option A: Direct Token (Development)**
1. Open `bot.py`
2. Replace `YOUR_BOT_TOKEN_HERE` with your actual bot token

**Option B: Environment Variables (Production - Recommended)**
1. Create a `.env` file or set environment variable:
```bash
export DISCORD_BOT_TOKEN="your_bot_token_here"
```

2. Update `bot.py` to use environment variables:
```python
import os
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
```

### Step 4: Run the Bot
```bash
python bot.py
```

You should see:
```
✅ Logged in as YourBotName
📊 Connected to X guilds
✅ Synced XX command(s)
```

## 🔧 Setup in Discord

### 1. Create Discord Bot
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application"
3. Go to "Bot" section and click "Add Bot"
4. Enable these Privileged Gateway Intents:
   - ✅ SERVER MEMBERS INTENT
   - ✅ MESSAGE CONTENT INTENT
   - ✅ PRESENCE INTENT (optional)
5. Copy your bot token

### 2. Invite Bot to Server
Use this URL (replace `YOUR_CLIENT_ID`):
```
https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=1099511627775&scope=bot%20applications.commands
```

### 3. Initial Server Setup
Run these commands in your Discord server:

```
/setup log_channel:#mod-logs mod_role:@Moderator admin_role:@Admin
/setautorole role:@Member
/config
```

## ⚙️ Configuration

### Bot Configuration (`config.json`)
The bot creates a `config.json` file automatically. You can modify these settings:

```json
{
    "mod_log_channel_id": null,
    "auto_role_id": null,
    "admin_role_ids": [],
    "mod_role_ids": [],
    "spam_threshold": 5,
    "spam_window": 5,
    "max_mentions": 5,
    "block_invites": true,
    "block_links": false
}
```

### Anti-Spam Settings
- `spam_threshold`: Number of messages to trigger spam detection (default: 5)
- `spam_window`: Time window in seconds (default: 5)
- `max_mentions`: Maximum mentions per message (default: 5)
- `block_invites`: Block Discord invite links (default: true)
- `block_links`: Block all external links (default: false)

## 📊 Database Structure

The bot uses SQLite with three tables:

**mod_logs** - All moderation actions
```sql
id, guild_id, user_id, moderator_id, action, reason, timestamp, duration
```

**active_punishments** - Temporary mutes/bans
```sql
id, guild_id, user_id, punishment_type, end_time, role_id
```

**warnings** - User warnings
```sql
id, guild_id, user_id, moderator_id, reason, timestamp
```

## 🌐 Hosting

### Free Hosting Options

**Replit.com**
1. Push your code to GitHub
2. Sign up at [replit.com](replit.com)
3. Import code from your repo
4. Add environment variable: `DISCORD_BOT_TOKEN`
5. Deploy!

**Other Options:**
- Fly.io
- Google Cloud (Free tier)
- PebbleHost
- Discloud.app

### Important for Production
- Use environment variables for sensitive data
- Consider PostgreSQL instead of SQLite for large servers
- Enable persistent storage for database
- Set up monitoring and error logging

## 🔒 Security Best Practices

1. **Never commit your token:**
```bash
# Add to .gitignore
config.json
moderation.db
.env
*.pyc
__pycache__/
```

2. **Use environment variables for production**

3. **Regularly update dependencies:**
```bash
pip install -U discord.py
```

4. **Backup your database regularly**

5. **Set appropriate bot permissions in Discord**

## 🛠️ Customization

### Adding Custom Commands
```python
@bot.tree.command(name="yourcommand", description="Your description")
@is_mod_or_admin()
async def your_command(interaction: discord.Interaction):
    await interaction.response.send_message("Your response")
```

### Customizing Embeds
```python
embed = discord.Embed(
    title="Custom Title",
    description="Custom description",
    color=discord.Color.blue()
)
embed.add_field(name="Field", value="Value")
await channel.send(embed=embed)
```

### Adjusting Anti-Spam
Edit the `CONFIG` dictionary in `bot.py`:
```python
CONFIG = {
    "spam_threshold": 5,     # Adjust this
    "spam_window": 5,        # Adjust this
    "max_mentions": 5,       # Adjust this
    "block_invites": True,
    "block_links": False,
}
```

## 🐛 Troubleshooting

### Bot not responding?
- Check if bot has proper permissions
- Verify commands are synced (`/help` should work)
- Ensure all intents are enabled in Developer Portal

### Commands not showing?
```python
# Force sync (add to on_ready temporarily)
await bot.tree.sync(guild=discord.Object(id=YOUR_GUILD_ID))
```

### Database errors?
- Delete `moderation.db` and restart
- Check file permissions

### Permission errors?
- Ensure bot role is above roles it manages
- Check "Manage Roles" permission is enabled

## 📈 Performance Tips

**For Large Servers (1000+ members):**
- Consider PostgreSQL instead of SQLite
- Implement more aggressive command cooldowns
- Use database indexing
- Monitor memory usage

**Rate Limiting:**
- Discord limits: 50 requests per second
- The bot handles this automatically

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with [discord.py](https://github.com/Rapptz/discord.py)

## 📸 Screenshots

![Bot Commands](https://via.placeholder.com/800x400?text=Add+Your+Screenshots+Here)
![Moderation Log](https://via.placeholder.com/800x400?text=Add+Your+Screenshots+Here)

## 🗺️ Roadmap

- [ ] Advanced analytics and statistics
- [ ] Custom automod rules
- [ ] Reaction roles system
- [ ] Leveling and XP system
- [ ] Multi-language support
- [ ] Machine learning spam detection

---

⭐ If you find this bot useful, please consider giving it a star!
