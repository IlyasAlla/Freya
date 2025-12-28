import discord
from discord import app_commands
from discord.ext import commands, tasks
import random
from typing import Literal
import os
import json
import sqlite3
import asyncio
from datetime import datetime, timedelta
from datetime import UTC
from typing import Optional, Literal
import re
from collections import defaultdict, deque
import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Bot configuration
BOT_TOKEN = os.getenv('DISCORD_TOKEN')

# Configure intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

# ==================== CONFIGURATION ====================
INTENTS = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=INTENTS)

# Configuration
CONFIG = {
    "mod_log_channel_id": None,  # Set this in /setup command
    "auto_role_id": None,  # Auto-assign role on join
    "admin_role_ids": [],  # Role IDs that can use admin commands
    "mod_role_ids": [],  # Role IDs that can use mod commands
    "spam_threshold": 5,  # Messages in spam_window to trigger anti-spam
    "spam_window": 5,  # Seconds to check for spam
    "max_mentions": 5,  # Max mentions per message
    "block_invites": True,
    "block_links": False,
}

# ==================== DATABASE SETUP ====================
def init_db():
    """Initialize SQLite database for moderation logs and warnings"""
    conn = sqlite3.connect('moderation.db')
    c = conn.cursor()
    
    # Moderation logs table
    c.execute('''CREATE TABLE IF NOT EXISTS mod_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        user_id INTEGER,
        moderator_id INTEGER,
        action TEXT,
        reason TEXT,
        timestamp TEXT,
        duration TEXT
    )''')
    
    # Active mutes/bans table
    c.execute('''CREATE TABLE IF NOT EXISTS active_punishments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        user_id INTEGER,
        punishment_type TEXT,
        end_time TEXT,
        role_id INTEGER
    )''')
    
    # Warnings table
    c.execute('''CREATE TABLE IF NOT EXISTS warnings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        user_id INTEGER,
        moderator_id INTEGER,
        reason TEXT,
        timestamp TEXT
    )''')
    
    conn.commit()
    conn.close()

# ==================== HELPER FUNCTIONS ====================
def load_config():
    """Load configuration from JSON file"""
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return CONFIG

def save_config(config):
    """Save configuration to JSON file"""
    with open('config.json', 'w') as f:
        json.dump(config, f, indent=4)

def log_action(guild_id, user_id, moderator_id, action, reason, duration=None):
    """Log moderation action to database"""
    conn = sqlite3.connect('moderation.db')
    c = conn.cursor()
    timestamp = datetime.utcnow().isoformat()
    c.execute('''INSERT INTO mod_logs (guild_id, user_id, moderator_id, action, reason, timestamp, duration)
                 VALUES (?, ?, ?, ?, ?, ?, ?)''',
              (guild_id, user_id, moderator_id, action, reason, timestamp, duration))
    conn.commit()
    conn.close()

def add_warning(guild_id, user_id, moderator_id, reason):
    """Add warning to database"""
    conn = sqlite3.connect('moderation.db')
    c = conn.cursor()
    timestamp = datetime.utcnow().isoformat()
    c.execute('''INSERT INTO warnings (guild_id, user_id, moderator_id, reason, timestamp)
                 VALUES (?, ?, ?, ?, ?)''',
              (guild_id, user_id, moderator_id, reason, timestamp))
    conn.commit()
    conn.close()

def get_warnings(guild_id, user_id):
    """Get all warnings for a user"""
    conn = sqlite3.connect('moderation.db')
    c = conn.cursor()
    c.execute('''SELECT moderator_id, reason, timestamp FROM warnings 
                 WHERE guild_id = ? AND user_id = ?''',
              (guild_id, user_id))
    warnings = c.fetchall()
    conn.close()
    return warnings

def get_mod_history(guild_id, user_id, limit=10):
    """Get moderation history for a user"""
    conn = sqlite3.connect('moderation.db')
    c = conn.cursor()
    c.execute('''SELECT action, reason, timestamp, moderator_id, duration 
                 FROM mod_logs 
                 WHERE guild_id = ? AND user_id = ? 
                 ORDER BY timestamp DESC LIMIT ?''',
              (guild_id, user_id, limit))
    history = c.fetchall()
    conn.close()
    return history

def parse_duration(duration_str: str) -> Optional[timedelta]:
    """Parse duration string (e.g., '1h', '30m', '2d') into timedelta"""
    match = re.match(r'(\d+)([smhd])', duration_str.lower())
    if not match:
        return None
    
    amount, unit = int(match.group(1)), match.group(2)
    if unit == 's':
        return timedelta(seconds=amount)
    elif unit == 'm':
        return timedelta(minutes=amount)
    elif unit == 'h':
        return timedelta(hours=amount)
    elif unit == 'd':
        return timedelta(days=amount)
    return None

async def send_log(guild, embed):
    """Send log embed to mod log channel"""
    config = load_config()
    if config.get("mod_log_channel_id"):
        channel = guild.get_channel(config["mod_log_channel_id"])
        if channel:
            await channel.send(embed=embed)

def create_log_embed(action: str, user: discord.User, moderator: discord.User, 
                     reason: str, duration: str = None, color: discord.Color = discord.Color.orange()):
    """Create a standard log embed"""
    embed = discord.Embed(
        title=f"🔨 {action}",
        color=color,
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="User", value=f"{user.mention} ({user.id})", inline=True)
    embed.add_field(name="Moderator", value=f"{moderator.mention}", inline=True)
    if duration:
        embed.add_field(name="Duration", value=duration, inline=True)
    embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
    embed.set_thumbnail(url=user.display_avatar.url)
    return embed

# ==================== PERMISSION CHECKS ====================
def is_mod_or_admin():
    """Check if user has mod or admin role"""
    async def predicate(interaction: discord.Interaction) -> bool:
        config = load_config()
        user_role_ids = [role.id for role in interaction.user.roles]
        allowed_roles = config.get("admin_role_ids", []) + config.get("mod_role_ids", [])
        
        # Check if user has administrator permission or allowed roles
        if interaction.user.guild_permissions.administrator:
            return True
        if any(role_id in allowed_roles for role_id in user_role_ids):
            return True
        
        # Send error embed
        embed = discord.Embed(
            title="❌ Permission Denied",
            description="You don't have permission to use this command!",
            color=discord.Color.red()
        )
        embed.add_field(
            name="Required Permission",
            value="**Moderator** or **Administrator** role",
            inline=False
        )
        embed.set_footer(text="Contact a server administrator if you believe this is an error")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return False
    return app_commands.check(predicate)

def is_admin():
    """Check if user has admin role"""
    async def predicate(interaction: discord.Interaction) -> bool:
        config = load_config()
        user_role_ids = [role.id for role in interaction.user.roles]
        allowed_roles = config.get("admin_role_ids", [])
        
        if interaction.user.guild_permissions.administrator:
            return True
        if any(role_id in allowed_roles for role_id in user_role_ids):
            return True
        
        # Send error embed
        embed = discord.Embed(
            title="❌ Permission Denied",
            description="You need administrator permissions to use this command!",
            color=discord.Color.red()
        )
        embed.add_field(
            name="Required Permission",
            value="**Administrator** role",
            inline=False
        )
        embed.set_footer(text="Contact a server administrator if you believe this is an error")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return False
    return app_commands.check(predicate)

# ==================== BOT EVENTS ====================
@bot.event
async def on_ready():
    """Bot startup event"""
    print(f'✅ Logged in as {bot.user.name} ({bot.user.id})')
    print(f'📊 Connected to {len(bot.guilds)} guilds')
    init_db()
    
    await bot.change_presence(activity=discord.Game(name="/help | Moderating Servers"))

    # Start background tasks
    check_punishments.start()
    
    # Sync commands
    try:
        synced = await bot.tree.sync()
        print(f'✅ Synced {len(synced)} command(s)')
    except Exception as e:
        print(f'❌ Failed to sync commands: {e}')

@bot.event
async def on_message(message: discord.Message):
    """Message event for anti-spam"""
    if message.guild is None or message.author.bot:
        return
    
    await check_spam(message)
    await bot.process_commands(message)

@bot.event
async def on_member_join(member: discord.Member):
    """Auto-assign role on member join"""
    config = load_config()
    if config.get("auto_role_id"):
        role = member.guild.get_role(config["auto_role_id"])
        if role:
            await member.add_roles(role)
            print(f'✅ Auto-assigned role to {member.name}')

# ==================== BACKGROUND TASKS ====================
@tasks.loop(minutes=1)
async def check_punishments():
    """Check and remove expired mutes/bans"""
    conn = sqlite3.connect('moderation.db')
    c = conn.cursor()
    
    current_time = datetime.utcnow().isoformat()
    c.execute('''SELECT id, guild_id, user_id, punishment_type, role_id 
                 FROM active_punishments 
                 WHERE end_time <= ?''', (current_time,))
    
    expired = c.fetchall()
    
    for punishment_id, guild_id, user_id, punishment_type, role_id in expired:
        guild = bot.get_guild(guild_id)
        if not guild:
            continue
        
        if punishment_type == "mute":
            member = guild.get_member(user_id)
            if member and role_id:
                role = guild.get_role(role_id)
                if role:
                    await member.remove_roles(role)
                    print(f'✅ Unmuted {member.name}')
        
        elif punishment_type == "ban":
            try:
                await guild.unban(discord.Object(id=user_id))
                print(f'✅ Unbanned user {user_id}')
            except:
                pass
        
        # Remove from database
        c.execute('DELETE FROM active_punishments WHERE id = ?', (punishment_id,))
    
    conn.commit()
    conn.close()

# ==================== MODERATION COMMANDS ====================
@bot.tree.command(name="mute", description="Mute a user indefinitely")
@app_commands.describe(user="The user to mute", reason="Reason for muting")
@is_mod_or_admin()
async def mute(interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
    """Mute a user indefinitely"""
    if user.top_role >= interaction.user.top_role and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You cannot mute this user!", ephemeral=True)
        return
    
    # Get or create mute role
    mute_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if not mute_role:
        mute_role = await interaction.guild.create_role(
            name="Muted",
            permissions=discord.Permissions(send_messages=False, speak=False)
        )
        # Set permissions for all channels
        for channel in interaction.guild.channels:
            await channel.set_permissions(mute_role, send_messages=False, speak=False)
    
    await user.add_roles(mute_role)
    log_action(interaction.guild.id, user.id, interaction.user.id, "Mute", reason)
    
    embed = create_log_embed("Mute", user, interaction.user, reason, color=discord.Color.orange())
    await send_log(interaction.guild, embed)
    
    await interaction.response.send_message(
        embed=discord.Embed(
            description=f"✅ {user.mention} has been muted.\n**Reason:** {reason}",
            color=discord.Color.green()
        )
    )

@bot.tree.command(name="tempmute", description="Temporarily mute a user")
@app_commands.describe(user="The user to mute", duration="Duration (e.g., 1h, 30m, 2d)", reason="Reason for muting")
@is_mod_or_admin()
async def tempmute(interaction: discord.Interaction, user: discord.Member, 
                   duration: str, reason: str = "No reason provided"):
    """Temporarily mute a user"""
    if user.top_role >= interaction.user.top_role and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You cannot mute this user!", ephemeral=True)
        return
    
    duration_delta = parse_duration(duration)
    if not duration_delta:
        await interaction.response.send_message("❌ Invalid duration format! Use: 1h, 30m, 2d", ephemeral=True)
        return
    
    # Get or create mute role
    mute_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if not mute_role:
        mute_role = await interaction.guild.create_role(
            name="Muted",
            permissions=discord.Permissions(send_messages=False, speak=False)
        )
        for channel in interaction.guild.channels:
            await channel.set_permissions(mute_role, send_messages=False, speak=False)
    
    await user.add_roles(mute_role)
    
    # Add to database
    end_time = (datetime.utcnow() + duration_delta).isoformat()
    conn = sqlite3.connect('moderation.db')
    c = conn.cursor()
    c.execute('''INSERT INTO active_punishments (guild_id, user_id, punishment_type, end_time, role_id)
                 VALUES (?, ?, ?, ?, ?)''',
              (interaction.guild.id, user.id, "mute", end_time, mute_role.id))
    conn.commit()
    conn.close()
    
    log_action(interaction.guild.id, user.id, interaction.user.id, "Temp Mute", reason, duration)
    
    embed = create_log_embed("Temporary Mute", user, interaction.user, reason, duration, discord.Color.orange())
    await send_log(interaction.guild, embed)
    
    await interaction.response.send_message(
        embed=discord.Embed(
            description=f"✅ {user.mention} has been muted for {duration}.\n**Reason:** {reason}",
            color=discord.Color.green()
        )
    )

@bot.tree.command(name="unmute", description="Unmute a user")
@app_commands.describe(user="The user to unmute")
@is_mod_or_admin()
async def unmute(interaction: discord.Interaction, user: discord.Member):
    """Unmute a user"""
    mute_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if not mute_role or mute_role not in user.roles:
        await interaction.response.send_message("❌ This user is not muted!", ephemeral=True)
        return
    
    await user.remove_roles(mute_role)
    
    # Remove from database
    conn = sqlite3.connect('moderation.db')
    c = conn.cursor()
    c.execute('DELETE FROM active_punishments WHERE guild_id = ? AND user_id = ? AND punishment_type = ?',
              (interaction.guild.id, user.id, "mute"))
    conn.commit()
    conn.close()
    
    log_action(interaction.guild.id, user.id, interaction.user.id, "Unmute", "Manual unmute")
    
    await interaction.response.send_message(
        embed=discord.Embed(
            description=f"✅ {user.mention} has been unmuted.",
            color=discord.Color.green()
        )
    )

@bot.tree.command(name="kick", description="Kick a user from the server")
@app_commands.describe(user="The user to kick", reason="Reason for kicking")
@is_mod_or_admin()
async def kick(interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
    """Kick a user"""
    if user.top_role >= interaction.user.top_role and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You cannot kick this user!", ephemeral=True)
        return
    
    log_action(interaction.guild.id, user.id, interaction.user.id, "Kick", reason)
    
    embed = create_log_embed("Kick", user, interaction.user, reason, color=discord.Color.red())
    await send_log(interaction.guild, embed)
    
    try:
        await user.send(f"You have been kicked from **{interaction.guild.name}**\n**Reason:** {reason}")
    except:
        pass
    
    await user.kick(reason=reason)
    
    await interaction.response.send_message(
        embed=discord.Embed(
            description=f"✅ {user.mention} has been kicked.\n**Reason:** {reason}",
            color=discord.Color.green()
        )
    )

@bot.tree.command(name="ban", description="Ban a user from the server")
@app_commands.describe(user="The user to ban", reason="Reason for banning", 
                      delete_messages="Delete message history (days, 0-7)")
@is_mod_or_admin()
async def ban(interaction: discord.Interaction, user: discord.Member, 
              reason: str = "No reason provided", delete_messages: int = 0):
    """Ban a user"""
    if user.top_role >= interaction.user.top_role and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You cannot ban this user!", ephemeral=True)
        return
    
    if delete_messages < 0 or delete_messages > 7:
        await interaction.response.send_message("❌ Delete messages must be between 0-7 days!", ephemeral=True)
        return
    
    log_action(interaction.guild.id, user.id, interaction.user.id, "Ban", reason)
    
    embed = create_log_embed("Ban", user, interaction.user, reason, color=discord.Color.dark_red())
    await send_log(interaction.guild, embed)
    
    try:
        await user.send(f"You have been banned from **{interaction.guild.name}**\n**Reason:** {reason}")
    except:
        pass
    
    await user.ban(reason=reason, delete_message_days=delete_messages)
    
    await interaction.response.send_message(
        embed=discord.Embed(
            description=f"✅ {user.mention} has been banned.\n**Reason:** {reason}",
            color=discord.Color.green()
        )
    )

@bot.tree.command(name="tempban", description="Temporarily ban a user")
@app_commands.describe(user="The user to ban", duration="Duration (e.g., 1h, 30m, 7d)", 
                      reason="Reason for banning")
@is_mod_or_admin()
async def tempban(interaction: discord.Interaction, user: discord.Member, 
                  duration: str, reason: str = "No reason provided"):
    """Temporarily ban a user"""
    if user.top_role >= interaction.user.top_role and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You cannot ban this user!", ephemeral=True)
        return
    
    duration_delta = parse_duration(duration)
    if not duration_delta:
        await interaction.response.send_message("❌ Invalid duration format! Use: 1h, 30m, 7d", ephemeral=True)
        return
    
    # Add to database
    end_time = (datetime.utcnow() + duration_delta).isoformat()
    conn = sqlite3.connect('moderation.db')
    c = conn.cursor()
    c.execute('''INSERT INTO active_punishments (guild_id, user_id, punishment_type, end_time, role_id)
                 VALUES (?, ?, ?, ?, ?)''',
              (interaction.guild.id, user.id, "ban", end_time, None))
    conn.commit()
    conn.close()
    
    log_action(interaction.guild.id, user.id, interaction.user.id, "Temp Ban", reason, duration)
    
    embed = create_log_embed("Temporary Ban", user, interaction.user, reason, duration, discord.Color.dark_red())
    await send_log(interaction.guild, embed)
    
    try:
        await user.send(
            f"You have been temporarily banned from **{interaction.guild.name}** for {duration}\n**Reason:** {reason}"
        )
    except:
        pass
    
    await user.ban(reason=reason)
    
    await interaction.response.send_message(
        embed=discord.Embed(
            description=f"✅ {user.mention} has been banned for {duration}.\n**Reason:** {reason}",
            color=discord.Color.green()
        )
    )

@bot.tree.command(name="unban", description="Unban a user")
@app_commands.describe(user_id="The ID of the user to unban")
@is_mod_or_admin()
async def unban(interaction: discord.Interaction, user_id: str):
    """Unban a user"""
    try:
        user_id = int(user_id)
        user = await bot.fetch_user(user_id)
        await interaction.guild.unban(user)
        
        # Remove from database
        conn = sqlite3.connect('moderation.db')
        c = conn.cursor()
        c.execute('DELETE FROM active_punishments WHERE guild_id = ? AND user_id = ? AND punishment_type = ?',
                  (interaction.guild.id, user_id, "ban"))
        conn.commit()
        conn.close()
        
        log_action(interaction.guild.id, user_id, interaction.user.id, "Unban", "Manual unban")
        
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"✅ {user.mention} has been unbanned.",
                color=discord.Color.green()
            )
        )
    except ValueError:
        await interaction.response.send_message("❌ Invalid user ID!", ephemeral=True)
    except discord.NotFound:
        await interaction.response.send_message("❌ User not found or not banned!", ephemeral=True)

@bot.tree.command(name="warn", description="Warn a user")
@app_commands.describe(user="The user to warn", reason="Reason for warning")
@is_mod_or_admin()
async def warn(interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
    """Warn a user"""
    add_warning(interaction.guild.id, user.id, interaction.user.id, reason)
    log_action(interaction.guild.id, user.id, interaction.user.id, "Warning", reason)
    
    warnings = get_warnings(interaction.guild.id, user.id)
    warning_count = len(warnings)
    
    embed = create_log_embed("Warning", user, interaction.user, reason, color=discord.Color.yellow())
    embed.add_field(name="Total Warnings", value=str(warning_count), inline=False)
    await send_log(interaction.guild, embed)
    
    try:
        await user.send(
            f"⚠️ You have been warned in **{interaction.guild.name}**\n"
            f"**Reason:** {reason}\n"
            f"**Total warnings:** {warning_count}"
        )
    except:
        pass
    
    await interaction.response.send_message(
        embed=discord.Embed(
            description=f"✅ {user.mention} has been warned.\n**Reason:** {reason}\n**Total warnings:** {warning_count}",
            color=discord.Color.green()
        )
    )

@bot.tree.command(name="warns", description="View warnings for a user")
@app_commands.describe(user="The user to check warnings for")
@is_mod_or_admin()
async def warns(interaction: discord.Interaction, user: discord.Member):
    """View user warnings"""
    warnings = get_warnings(interaction.guild.id, user.id)
    
    if not warnings:
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"✅ {user.mention} has no warnings!",
                color=discord.Color.green()
            ),
            ephemeral=True
        )
        return
    
    embed = discord.Embed(
        title=f"⚠️ Warnings for {user.name}",
        color=discord.Color.yellow(),
        timestamp=datetime.utcnow()
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    
    for i, (mod_id, reason, timestamp) in enumerate(warnings[:10], 1):
        moderator = interaction.guild.get_member(mod_id) or await bot.fetch_user(mod_id)
        time_str = datetime.fromisoformat(timestamp).strftime("%Y-%m-%d %H:%M")
        embed.add_field(
            name=f"Warning #{i} - {time_str}",
            value=f"**Moderator:** {moderator.mention}\n**Reason:** {reason}",
            inline=False
        )
    
    embed.set_footer(text=f"Total warnings: {len(warnings)}")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="clearwarns", description="Clear all warnings for a user")
@app_commands.describe(user="The user to clear warnings for")
@is_admin()
async def clearwarns(interaction: discord.Interaction, user: discord.Member):
    """Clear all warnings for a user"""
    conn = sqlite3.connect('moderation.db')
    c = conn.cursor()
    c.execute('DELETE FROM warnings WHERE guild_id = ? AND user_id = ?',
              (interaction.guild.id, user.id))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    
    log_action(interaction.guild.id, user.id, interaction.user.id, "Clear Warnings", 
               f"Cleared {deleted} warnings")
    
    await interaction.response.send_message(
        embed=discord.Embed(
            description=f"✅ Cleared {deleted} warning(s) for {user.mention}",
            color=discord.Color.green()
        )
    )

@bot.tree.command(name="modlog", description="View moderation history for a user")
@app_commands.describe(user="The user to check history for", limit="Number of entries to show (max 20)")
@is_mod_or_admin()
async def modlog(interaction: discord.Interaction, user: discord.Member, limit: int = 10):
    """View moderation history"""
    if limit > 20:
        limit = 20
    
    history = get_mod_history(interaction.guild.id, user.id, limit)
    
    if not history:
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"✅ {user.mention} has no moderation history!",
                color=discord.Color.green()
            ),
            ephemeral=True
        )
        return
    
    embed = discord.Embed(
        title=f"📋 Moderation Log for {user.name}",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    
    for action, reason, timestamp, mod_id, duration in history:
        moderator = interaction.guild.get_member(mod_id) or await bot.fetch_user(mod_id)
        time_str = datetime.fromisoformat(timestamp).strftime("%Y-%m-%d %H:%M")
        
        field_value = f"**Moderator:** {moderator.mention}\n**Reason:** {reason}"
        if duration:
            field_value += f"\n**Duration:** {duration}"
        
        embed.add_field(
            name=f"{action} - {time_str}",
            value=field_value,
            inline=False
        )
    
    embed.set_footer(text=f"Showing last {len(history)} action(s)")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ==================== ROLE MANAGEMENT ====================
@bot.tree.command(name="addrole", description="Add a role to a user")
@app_commands.describe(user="The user to add role to", role="The role to add")
@is_mod_or_admin()
async def addrole(interaction: discord.Interaction, user: discord.Member, role: discord.Role):
    """Add role to user"""
    if role >= interaction.guild.me.top_role:
        await interaction.response.send_message("❌ I cannot manage this role!", ephemeral=True)
        return
    
    if role in user.roles:
        await interaction.response.send_message(f"❌ {user.mention} already has this role!", ephemeral=True)
        return
    
    await user.add_roles(role)
    log_action(interaction.guild.id, user.id, interaction.user.id, "Role Added", f"Added role: {role.name}")
    
    await interaction.response.send_message(
        embed=discord.Embed(
            description=f"✅ Added role {role.mention} to {user.mention}",
            color=discord.Color.green()
        )
    )

@bot.tree.command(name="removerole", description="Remove a role from a user")
@app_commands.describe(user="The user to remove role from", role="The role to remove")
@is_mod_or_admin()
async def removerole(interaction: discord.Interaction, user: discord.Member, role: discord.Role):
    """Remove role from user"""
    if role >= interaction.guild.me.top_role:
        await interaction.response.send_message("❌ I cannot manage this role!", ephemeral=True)
        return
    
    if role not in user.roles:
        await interaction.response.send_message(f"❌ {user.mention} doesn't have this role!", ephemeral=True)
        return
    
    await user.remove_roles(role)
    log_action(interaction.guild.id, user.id, interaction.user.id, "Role Removed", f"Removed role: {role.name}")
    
    await interaction.response.send_message(
        embed=discord.Embed(
            description=f"✅ Removed role {role.mention} from {user.mention}",
            color=discord.Color.green()
        )
    )

# ==================== NICKNAME MANAGEMENT ====================
@bot.tree.command(name="setnick", description="Set a user's nickname")
@app_commands.describe(user="The user to set nickname for", nickname="The new nickname")
@is_mod_or_admin()
async def setnick(interaction: discord.Interaction, user: discord.Member, nickname: str):
    """Set user nickname"""
    if user.top_role >= interaction.user.top_role and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You cannot change this user's nickname!", ephemeral=True)
        return
    
    old_nick = user.display_name
    await user.edit(nick=nickname)
    log_action(interaction.guild.id, user.id, interaction.user.id, "Nickname Changed", 
               f"Changed from '{old_nick}' to '{nickname}'")
    
    await interaction.response.send_message(
        embed=discord.Embed(
            description=f"✅ Changed {user.mention}'s nickname to **{nickname}**",
            color=discord.Color.green()
        )
    )

@bot.tree.command(name="resetnick", description="Reset a user's nickname")
@app_commands.describe(user="The user to reset nickname for")
@is_mod_or_admin()
async def resetnick(interaction: discord.Interaction, user: discord.Member):
    """Reset user nickname"""
    if user.top_role >= interaction.user.top_role and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You cannot change this user's nickname!", ephemeral=True)
        return
    
    await user.edit(nick=None)
    log_action(interaction.guild.id, user.id, interaction.user.id, "Nickname Reset", "Reset to default")
    
    await interaction.response.send_message(
        embed=discord.Embed(
            description=f"✅ Reset {user.mention}'s nickname",
            color=discord.Color.green()
        )
    )

# ==================== CONFIGURATION COMMANDS ====================
@bot.tree.command(name="setup", description="Setup the bot for this server")
@app_commands.describe(
    log_channel="Channel for moderation logs",
    mod_role="Role for moderators",
    admin_role="Role for administrators"
)
@is_admin()
async def setup(interaction: discord.Interaction, 
                log_channel: discord.TextChannel,
                mod_role: Optional[discord.Role] = None,
                admin_role: Optional[discord.Role] = None):
    """Setup bot configuration"""
    config = load_config()
    config["mod_log_channel_id"] = log_channel.id
    
    if mod_role:
        if "mod_role_ids" not in config:
            config["mod_role_ids"] = []
        if mod_role.id not in config["mod_role_ids"]:
            config["mod_role_ids"].append(mod_role.id)
    
    if admin_role:
        if "admin_role_ids" not in config:
            config["admin_role_ids"] = []
        if admin_role.id not in config["admin_role_ids"]:
            config["admin_role_ids"].append(admin_role.id)
    
    save_config(config)
    
    embed = discord.Embed(
        title="✅ Bot Setup Complete",
        color=discord.Color.green(),
        description="The moderation bot has been configured!"
    )
    embed.add_field(name="Log Channel", value=log_channel.mention, inline=False)
    if mod_role:
        embed.add_field(name="Moderator Role", value=mod_role.mention, inline=True)
    if admin_role:
        embed.add_field(name="Admin Role", value=admin_role.mention, inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="setautorole", description="Set role to auto-assign on member join")
@app_commands.describe(role="Role to auto-assign")
@is_admin()
async def setautorole(interaction: discord.Interaction, role: discord.Role):
    """Set auto-assign role"""
    config = load_config()
    config["auto_role_id"] = role.id
    save_config(config)
    
    await interaction.response.send_message(
        embed=discord.Embed(
            description=f"✅ Will auto-assign {role.mention} to new members",
            color=discord.Color.green()
        )
    )

@bot.tree.command(name="config", description="View current bot configuration")
@is_admin()
async def view_config(interaction: discord.Interaction):
    """View bot configuration"""
    config = load_config()
    
    embed = discord.Embed(
        title="⚙️ Bot Configuration",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    
    # Log channel
    log_channel_id = config.get("mod_log_channel_id")
    log_channel = interaction.guild.get_channel(log_channel_id) if log_channel_id else None
    embed.add_field(
        name="Log Channel",
        value=log_channel.mention if log_channel else "Not set",
        inline=False
    )
    
    # Auto role
    auto_role_id = config.get("auto_role_id")
    auto_role = interaction.guild.get_role(auto_role_id) if auto_role_id else None
    embed.add_field(
        name="Auto-assign Role",
        value=auto_role.mention if auto_role else "Not set",
        inline=False
    )
    
    # Mod roles
    mod_roles = [interaction.guild.get_role(r) for r in config.get("mod_role_ids", [])]
    mod_roles = [r.mention for r in mod_roles if r]
    embed.add_field(
        name="Moderator Roles",
        value=", ".join(mod_roles) if mod_roles else "Not set",
        inline=False
    )
    
    # Admin roles
    admin_roles = [interaction.guild.get_role(r) for r in config.get("admin_role_ids", [])]
    admin_roles = [r.mention for r in admin_roles if r]
    embed.add_field(
        name="Admin Roles",
        value=", ".join(admin_roles) if admin_roles else "Not set",
        inline=False
    )
    
    # Anti-spam settings
    embed.add_field(
        name="Anti-Spam Settings",
        value=f"Threshold: {config['spam_threshold']} messages\n"
              f"Window: {config['spam_window']} seconds\n"
              f"Max Mentions: {config['max_mentions']}\n"
              f"Block Invites: {'Yes' if config['block_invites'] else 'No'}\n"
              f"Block Links: {'Yes' if config['block_links'] else 'No'}",
        inline=False
    )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ==================== UTILITY COMMANDS ====================
@bot.tree.command(name="userinfo", description="Get information about a user")
@app_commands.describe(user="The user to get info about")
async def userinfo(interaction: discord.Interaction, user: Optional[discord.Member] = None):
    """Get user information"""
    user = user or interaction.user
    
    embed = discord.Embed(
        title=f"User Info - {user.name}",
        color=user.color,
        timestamp=datetime.utcnow()
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    
    embed.add_field(name="ID", value=user.id, inline=True)
    embed.add_field(name="Nickname", value=user.display_name, inline=True)
    embed.add_field(name="Bot", value="Yes" if user.bot else "No", inline=True)
    
    embed.add_field(name="Account Created", 
                   value=user.created_at.strftime("%Y-%m-%d %H:%M:%S"), 
                   inline=False)
    embed.add_field(name="Joined Server", 
                   value=user.joined_at.strftime("%Y-%m-%d %H:%M:%S") if user.joined_at else "Unknown", 
                   inline=False)
    
    roles = [role.mention for role in user.roles if role.name != "@everyone"]
    embed.add_field(name=f"Roles ({len(roles)})", 
                   value=" ".join(roles) if roles else "No roles", 
                   inline=False)
    
    # Add moderation stats
    warnings = get_warnings(interaction.guild.id, user.id)
    history = get_mod_history(interaction.guild.id, user.id, 5)
    embed.add_field(name="Warnings", value=str(len(warnings)), inline=True)
    embed.add_field(name="Mod Actions", value=str(len(history)), inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="serverinfo", description="Get information about the server")
async def serverinfo(interaction: discord.Interaction):
    """Get server information"""
    guild = interaction.guild
    
    embed = discord.Embed(
        title=f"Server Info - {guild.name}",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    
    embed.add_field(name="ID", value=guild.id, inline=True)
    embed.add_field(name="Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
    embed.add_field(name="Created", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)
    
    embed.add_field(name="Members", value=guild.member_count, inline=True)
    embed.add_field(name="Roles", value=len(guild.roles), inline=True)
    embed.add_field(name="Channels", value=len(guild.channels), inline=True)
    
    embed.add_field(name="Boost Level", value=f"Level {guild.premium_tier}", inline=True)
    embed.add_field(name="Boosts", value=guild.premium_subscription_count, inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="purge", description="Delete multiple messages")
@app_commands.describe(amount="Number of messages to delete (1-100)")
@is_mod_or_admin()
async def purge(interaction: discord.Interaction, amount: int):
    """Bulk delete messages"""
    if amount < 1 or amount > 100:
        await interaction.response.send_message("❌ Amount must be between 1 and 100!", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    
    log_action(interaction.guild.id, interaction.user.id, interaction.user.id, 
               "Purge", f"Deleted {len(deleted)} messages in {interaction.channel.mention}")
    
    await interaction.followup.send(
        embed=discord.Embed(
            description=f"✅ Deleted {len(deleted)} message(s)",
            color=discord.Color.green()
        ),
        ephemeral=True
    )

@bot.tree.command(name="slowmode", description="Set slowmode for a channel")
@app_commands.describe(seconds="Delay between messages (0-21600 seconds)")
@is_mod_or_admin()
async def slowmode(interaction: discord.Interaction, seconds: int):
    """Set channel slowmode"""
    if seconds < 0 or seconds > 21600:
        await interaction.response.send_message("❌ Slowmode must be between 0 and 21600 seconds!", ephemeral=True)
        return
    
    await interaction.channel.edit(slowmode_delay=seconds)
    
    if seconds == 0:
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"✅ Slowmode disabled in {interaction.channel.mention}",
                color=discord.Color.green()
            )
        )
    else:
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"✅ Slowmode set to {seconds} seconds in {interaction.channel.mention}",
                color=discord.Color.green()
            )
        )

@bot.tree.command(name="lockdown", description="Lock or unlock a channel")
@app_commands.describe(lock="Lock (True) or unlock (False) the channel")
@is_mod_or_admin()
async def lockdown(interaction: discord.Interaction, lock: bool):
    """Lock/unlock channel"""
    everyone_role = interaction.guild.default_role
    
    if lock:
        await interaction.channel.set_permissions(everyone_role, send_messages=False)
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"🔒 {interaction.channel.mention} has been locked",
                color=discord.Color.red()
            )
        )
    else:
        await interaction.channel.set_permissions(everyone_role, send_messages=None)
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"🔓 {interaction.channel.mention} has been unlocked",
                color=discord.Color.green()
            )
        )

# ==================== HELP COMMAND ====================
@bot.tree.command(name="help", description="Show all available commands")
@app_commands.describe(category="Filter commands by category")
@app_commands.choices(category=[
    app_commands.Choice(name="Moderation", value="moderation"),
    app_commands.Choice(name="Voice Management", value="voice"),
    app_commands.Choice(name="Role Management", value="roles"),
    app_commands.Choice(name="Utility & Info", value="utility"),
    app_commands.Choice(name="Fun Commands", value="fun"),
    app_commands.Choice(name="Configuration", value="config"),
    app_commands.Choice(name="All", value="all")
])
async def help_command(interaction: discord.Interaction, category: str = "all"):
    """Show help menu"""
    embed = discord.Embed(
        title="🤖 Moderation Bot Help",
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow()
    )
    
    if category in ["all", "moderation"]:
        embed.add_field(
            name="🔨 Moderation Commands",
            value=(
                "`/mute` - Mute a user indefinitely\n"
                "`/tempmute` - Temporarily mute a user\n"
                "`/unmute` - Unmute a user\n"
                "`/timeout` - Timeout a user (Discord native)\n"
                "`/untimeout` - Remove timeout from user\n"
                "`/kick` - Kick a user\n"
                "`/ban` - Ban a user permanently\n"
                "`/tempban` - Temporarily ban a user\n"
                "`/unban` - Unban a user\n"
                "`/warn` - Warn a user\n"
                "`/warns` - View user warnings\n"
                "`/clearwarns` - Clear user warnings\n"
                "`/modlog` - View moderation history\n"
                "`/purge` - Delete multiple messages\n"
                "`/clear` - Advanced message deletion with filters\n"
                "`/slowmode` - Set channel slowmode\n"
                "`/lockdown` - Lock/unlock a channel\n"
                "`/movemsg` - Move messages to another channel\n"
                "`/whois` - Detailed user information"
            ),
            inline=False
        )
    
    if category in ["all", "voice"]:
        embed.add_field(
            name="🔊 Voice Management",
            value=(
                "`/voicemove` - Move user to voice channel\n"
                "`/voicekick` - Kick user from voice\n"
                "`/vcmute` - Mute user in voice channel\n"
                "`/vcunmute` - Unmute user in voice\n"
                "`/vcdeafen` - Deafen user in voice\n"
                "`/vcundeafen` - Undeafen user in voice"
            ),
            inline=False
        )
    
    if category in ["all", "roles"]:
        embed.add_field(
            name="👥 Role Management",
            value=(
                "`/addrole` - Add a role to a user\n"
                "`/removerole` - Remove a role from a user\n"
                "`/setnick` - Set user nickname\n"
                "`/resetnick` - Reset user nickname"
            ),
            inline=False
        )
    
    if category in ["all", "utility"]:
        embed.add_field(
            name="🔧 Utility & Info Commands",
            value=(
                "`/userinfo` - Get user information\n"
                "`/serverinfo` - Get server information\n"
                "`/avatar` - Display user's avatar\n"
                "`/banner` - Display user's banner\n"
                "`/roles` - List all server roles\n"
                "`/embed` - Create custom embeds\n"
                "`/announce` - Send announcements\n"
                "`/poll` - Create polls with reactions\n"
                "`/help` - Show this help menu"
            ),
            inline=False
        )
    
    if category in ["all", "fun"]:
        embed.add_field(
            name="🎮 Fun Commands",
            value=(
                "`/8ball` - Ask the magic 8-ball\n"
                "`/coinflip` - Flip a coin\n"
                "`/roll` - Roll dice"
            ),
            inline=False
        )
    
    if category in ["all", "config"]:
        embed.add_field(
            name="⚙️ Configuration",
            value=(
                "`/setup` - Initial bot setup\n"
                "`/setautorole` - Set auto-assign role\n"
                "`/config` - View current configuration"
            ),
            inline=False
        )
    
    embed.set_footer(text="Use /help <category> to filter commands")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ==================== TIMEOUT COMMAND (Discord Native) ====================
@bot.tree.command(name="timeout", description="Timeout a user (Discord native timeout)")
@app_commands.describe(
    user="The user to timeout",
    duration="Duration (e.g., 1h, 30m, 1d)",
    reason="Reason for timeout"
)
@is_mod_or_admin()
async def timeout(interaction: discord.Interaction, user: discord.Member, 
                  duration: str, reason: str = "No reason provided"):
    """Timeout a user using Discord's native timeout feature"""
    if user.top_role >= interaction.user.top_role and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You cannot timeout this user!", ephemeral=True)
        return
    
    duration_delta = parse_duration(duration)
    if not duration_delta:
        await interaction.response.send_message("❌ Invalid duration format! Use: 1h, 30m, 1d", ephemeral=True)
        return
    
    if duration_delta > timedelta(days=28):
        await interaction.response.send_message("❌ Maximum timeout duration is 28 days!", ephemeral=True)
        return
    
    await user.timeout(duration_delta, reason=reason)
    log_action(interaction.guild.id, user.id, interaction.user.id, "Timeout", reason, duration)
    
    embed = create_log_embed("Timeout", user, interaction.user, reason, duration, discord.Color.orange())
    await send_log(interaction.guild, embed)
    
    await interaction.response.send_message(
        embed=discord.Embed(
            description=f"✅ {user.mention} has been timed out for {duration}.\n**Reason:** {reason}",
            color=discord.Color.green()
        )
    )

@bot.tree.command(name="untimeout", description="Remove timeout from a user")
@app_commands.describe(user="The user to remove timeout from")
@is_mod_or_admin()
async def untimeout(interaction: discord.Interaction, user: discord.Member):
    """Remove timeout from user"""
    if not user.is_timed_out():
        await interaction.response.send_message("❌ This user is not timed out!", ephemeral=True)
        return
    
    await user.timeout(None)
    log_action(interaction.guild.id, user.id, interaction.user.id, "Timeout Removed", "Manual removal")
    
    await interaction.response.send_message(
        embed=discord.Embed(
            description=f"✅ Removed timeout from {user.mention}",
            color=discord.Color.green()
        )
    )

# ==================== ADVANCED CLEAR COMMAND ====================
@bot.tree.command(name="clear", description="Advanced message deletion with filters")
@app_commands.describe(
    amount="Number of messages to check (1-100)",
    user="Only delete messages from this user",
    contains="Only delete messages containing this text",
    bots="Only delete bot messages"
)
@is_mod_or_admin()
async def clear(interaction: discord.Interaction, amount: int, 
                user: Optional[discord.Member] = None,
                contains: Optional[str] = None,
                bots: Optional[bool] = None):
    """Advanced message clearing with filters"""
    if amount < 1 or amount > 100:
        await interaction.response.send_message("❌ Amount must be between 1 and 100!", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    def check(message):
        if user and message.author != user:
            return False
        if contains and contains.lower() not in message.content.lower():
            return False
        if bots is not None:
            if bots and not message.author.bot:
                return False
            if not bots and message.author.bot:
                return False
        return True
    
    deleted = await interaction.channel.purge(limit=amount, check=check)
    
    filter_desc = []
    if user:
        filter_desc.append(f"from {user.mention}")
    if contains:
        filter_desc.append(f"containing '{contains}'")
    if bots:
        filter_desc.append("from bots")
    
    filter_text = " " + " ".join(filter_desc) if filter_desc else ""
    
    log_action(interaction.guild.id, interaction.user.id, interaction.user.id, 
               "Clear", f"Deleted {len(deleted)} messages{filter_text} in {interaction.channel.mention}")
    
    await interaction.followup.send(
        embed=discord.Embed(
            description=f"✅ Deleted {len(deleted)} message(s){filter_text}",
            color=discord.Color.green()
        ),
        ephemeral=True
    )

# ==================== AVATAR & BANNER COMMANDS ====================
@bot.tree.command(name="avatar", description="Display user's avatar")
@app_commands.describe(user="User to show avatar for")
async def avatar(interaction: discord.Interaction, user: Optional[discord.Member] = None):
    """Show user avatar"""
    user = user or interaction.user
    
    embed = discord.Embed(
        title=f"{user.name}'s Avatar",
        color=user.color,
        timestamp=discord.utils.utcnow()
    )
    
    avatar_url = user.display_avatar.url
    embed.set_image(url=avatar_url)
    embed.add_field(name="Avatar URL", value=f"[Click Here]({avatar_url})", inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="banner", description="Display user's banner")
@app_commands.describe(user="User to show banner for")
async def banner(interaction: discord.Interaction, user: Optional[discord.Member] = None):
    """Show user banner"""
    user = user or interaction.user
    fetched_user = await bot.fetch_user(user.id)
    
    if not fetched_user.banner:
        await interaction.response.send_message(
            f"❌ {user.mention} doesn't have a banner set!",
            ephemeral=True
        )
        return
    
    embed = discord.Embed(
        title=f"{user.name}'s Banner",
        color=user.color,
        timestamp=discord.utils.utcnow()
    )
    
    banner_url = fetched_user.banner.url
    embed.set_image(url=banner_url)
    embed.add_field(name="Banner URL", value=f"[Click Here]({banner_url})", inline=False)
    
    await interaction.response.send_message(embed=embed)

# ==================== ROLES LIST COMMAND ====================
@bot.tree.command(name="roles", description="List all server roles")
async def roles_list(interaction: discord.Interaction):
    """List all server roles"""
    roles = sorted(interaction.guild.roles, key=lambda r: r.position, reverse=True)
    
    embed = discord.Embed(
        title=f"Roles in {interaction.guild.name}",
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow()
    )
    
    role_list = []
    for role in roles:
        if role.name != "@everyone":
            member_count = len(role.members)
            role_list.append(f"{role.mention} - {member_count} members")
    
    # Split into chunks if too long
    if len(role_list) > 25:
        role_list = role_list[:25]
        embed.set_footer(text=f"Showing first 25 of {len(roles)-1} roles")
    
    for i in range(0, len(role_list), 10):
        chunk = role_list[i:i+10]
        embed.add_field(
            name=f"Roles {i+1}-{i+len(chunk)}",
            value="\n".join(chunk),
            inline=False
        )
    
    await interaction.response.send_message(embed=embed)

# ==================== EMBED COMMAND ====================
@bot.tree.command(name="embed", description="Create a custom embed message")
@app_commands.describe(
    title="Embed title",
    description="Embed description",
    color="Embed color (red, blue, green, etc.)",
    channel="Channel to send to (optional)"
)
@is_mod_or_admin()
async def create_embed(interaction: discord.Interaction, title: str, description: str,
                       color: Optional[str] = "blue",
                       channel: Optional[discord.TextChannel] = None):
    """Create custom embed"""
    # Color mapping
    color_map = {
        "red": discord.Color.red(),
        "blue": discord.Color.blue(),
        "green": discord.Color.green(),
        "yellow": discord.Color.yellow(),
        "orange": discord.Color.orange(),
        "purple": discord.Color.purple(),
        "gold": discord.Color.gold(),
    }
    
    embed_color = color_map.get(color.lower(), discord.Color.blue())
    
    embed = discord.Embed(
        title=title,
        description=description,
        color=embed_color,
        timestamp=discord.utils.utcnow()
    )
    embed.set_footer(text=f"Created by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
    
    target_channel = channel or interaction.channel
    await target_channel.send(embed=embed)
    
    await interaction.response.send_message(
        f"✅ Embed sent to {target_channel.mention}",
        ephemeral=True
    )

# ==================== ANNOUNCE COMMAND ====================
@bot.tree.command(name="announce", description="Send an announcement")
@app_commands.describe(
    channel="Channel to announce in",
    title="Announcement title",
    message="Announcement message",
    ping_everyone="Ping @everyone (optional)"
)
@is_admin()
async def announce(interaction: discord.Interaction, channel: discord.TextChannel,
                   title: str, message: str, ping_everyone: bool = False):
    """Send announcement"""
    embed = discord.Embed(
        title=f"📢 {title}",
        description=message,
        color=discord.Color.gold(),
        timestamp=discord.utils.utcnow()
    )
    embed.set_footer(text=f"Announced by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
    
    content = "@everyone" if ping_everyone else None
    await channel.send(content=content, embed=embed)
    
    await interaction.response.send_message(
        f"✅ Announcement sent to {channel.mention}",
        ephemeral=True
    )

# ==================== POLL COMMAND ====================
@bot.tree.command(name="poll", description="Create a poll")
@app_commands.describe(
    question="Poll question",
    option1="First option",
    option2="Second option",
    option3="Third option (optional)",
    option4="Fourth option (optional)",
    option5="Fifth option (optional)"
)
async def poll(interaction: discord.Interaction, question: str,
               option1: str, option2: str,
               option3: Optional[str] = None,
               option4: Optional[str] = None,
               option5: Optional[str] = None):
    """Create a poll with reactions"""
    options = [option1, option2]
    if option3:
        options.append(option3)
    if option4:
        options.append(option4)
    if option5:
        options.append(option5)
    
    # Emoji numbers
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    
    embed = discord.Embed(
        title=f"📊 {question}",
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow()
    )
    
    description = "\n".join([f"{emojis[i]} {opt}" for i, opt in enumerate(options)])
    embed.description = description
    embed.set_footer(text=f"Poll by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
    
    await interaction.response.send_message(embed=embed)
    message = await interaction.original_response()
    
    # Add reactions
    for i in range(len(options)):
        await message.add_reaction(emojis[i])

# ==================== FUN COMMANDS ====================
@bot.tree.command(name="8ball", description="Ask the magic 8-ball a question")
@app_commands.describe(question="Your yes/no question")
async def eightball(interaction: discord.Interaction, question: str):
    """Magic 8-ball"""
    responses = [
        "🎱 It is certain.",
        "🎱 It is decidedly so.",
        "🎱 Without a doubt.",
        "🎱 Yes definitely.",
        "🎱 You may rely on it.",
        "🎱 As I see it, yes.",
        "🎱 Most likely.",
        "🎱 Outlook good.",
        "🎱 Yes.",
        "🎱 Signs point to yes.",
        "🎱 Reply hazy, try again.",
        "🎱 Ask again later.",
        "🎱 Better not tell you now.",
        "🎱 Cannot predict now.",
        "🎱 Concentrate and ask again.",
        "🎱 Don't count on it.",
        "🎱 My reply is no.",
        "🎱 My sources say no.",
        "🎱 Outlook not so good.",
        "🎱 Very doubtful."
    ]
    
    embed = discord.Embed(
        title="Magic 8-Ball",
        color=discord.Color.purple()
    )
    embed.add_field(name="Question", value=question, inline=False)
    embed.add_field(name="Answer", value=random.choice(responses), inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="coinflip", description="Flip a coin")
async def coinflip(interaction: discord.Interaction):
    """Flip a coin"""
    result = random.choice(["Heads", "Tails"])
    emoji = "🪙"
    
    embed = discord.Embed(
        title=f"{emoji} Coin Flip",
        description=f"The coin landed on: **{result}**",
        color=discord.Color.gold()
    )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="roll", description="Roll dice")
@app_commands.describe(sides="Number of sides on the die (default: 6)")
async def roll(interaction: discord.Interaction, sides: int = 6):
    """Roll a die"""
    if sides < 2 or sides > 100:
        await interaction.response.send_message("❌ Dice must have between 2 and 100 sides!", ephemeral=True)
        return
    
    result = random.randint(1, sides)
    
    embed = discord.Embed(
        title="🎲 Dice Roll",
        description=f"You rolled a **{result}** on a {sides}-sided die!",
        color=discord.Color.blue()
    )
    
    await interaction.response.send_message(embed=embed)

# ==================== VOICE CHANNEL MANAGEMENT ====================
@bot.tree.command(name="voicemove", description="Move user to another voice channel")
@app_commands.describe(user="User to move", channel="Voice channel to move to")
@is_mod_or_admin()
async def voicemove(interaction: discord.Interaction, user: discord.Member, 
                    channel: discord.VoiceChannel):
    """Move user to voice channel"""
    if not user.voice:
        await interaction.response.send_message("❌ User is not in a voice channel!", ephemeral=True)
        return
    
    await user.move_to(channel)
    log_action(interaction.guild.id, user.id, interaction.user.id, 
               "Voice Move", f"Moved to {channel.name}")
    
    await interaction.response.send_message(
        embed=discord.Embed(
            description=f"✅ Moved {user.mention} to {channel.mention}",
            color=discord.Color.green()
        )
    )

@bot.tree.command(name="voicekick", description="Kick user from voice channel")
@app_commands.describe(user="User to kick from voice")
@is_mod_or_admin()
async def voicekick(interaction: discord.Interaction, user: discord.Member):
    """Kick user from voice"""
    if not user.voice:
        await interaction.response.send_message("❌ User is not in a voice channel!", ephemeral=True)
        return
    
    await user.move_to(None)
    log_action(interaction.guild.id, user.id, interaction.user.id, 
               "Voice Kick", "Kicked from voice channel")
    
    await interaction.response.send_message(
        embed=discord.Embed(
            description=f"✅ Kicked {user.mention} from voice channel",
            color=discord.Color.green()
        )
    )

@bot.tree.command(name="vcmute", description="Mute user in voice channel")
@app_commands.describe(user="User to mute")
@is_mod_or_admin()
async def vcmute(interaction: discord.Interaction, user: discord.Member):
    """Voice channel mute"""
    if not user.voice:
        await interaction.response.send_message("❌ User is not in a voice channel!", ephemeral=True)
        return
    
    await user.edit(mute=True)
    log_action(interaction.guild.id, user.id, interaction.user.id, 
               "Voice Mute", "Muted in voice channel")
    
    await interaction.response.send_message(
        embed=discord.Embed(
            description=f"✅ Muted {user.mention} in voice channel",
            color=discord.Color.green()
        )
    )

@bot.tree.command(name="vcunmute", description="Unmute user in voice channel")
@app_commands.describe(user="User to unmute")
@is_mod_or_admin()
async def vcunmute(interaction: discord.Interaction, user: discord.Member):
    """Voice channel unmute"""
    if not user.voice:
        await interaction.response.send_message("❌ User is not in a voice channel!", ephemeral=True)
        return
    
    await user.edit(mute=False)
    log_action(interaction.guild.id, user.id, interaction.user.id, 
               "Voice Unmute", "Unmuted in voice channel")
    
    await interaction.response.send_message(
        embed=discord.Embed(
            description=f"✅ Unmuted {user.mention} in voice channel",
            color=discord.Color.green()
        )
    )

@bot.tree.command(name="vcdeafen", description="Deafen user in voice channel")
@app_commands.describe(user="User to deafen")
@is_mod_or_admin()
async def vcdeafen(interaction: discord.Interaction, user: discord.Member):
    """Voice channel deafen"""
    if not user.voice:
        await interaction.response.send_message("❌ User is not in a voice channel!", ephemeral=True)
        return
    
    await user.edit(deafen=True)
    log_action(interaction.guild.id, user.id, interaction.user.id, 
               "Voice Deafen", "Deafened in voice channel")
    
    await interaction.response.send_message(
        embed=discord.Embed(
            description=f"✅ Deafened {user.mention} in voice channel",
            color=discord.Color.green()
        )
    )

@bot.tree.command(name="vcundeafen", description="Undeafen user in voice channel")
@app_commands.describe(user="User to undeafen")
@is_mod_or_admin()
async def vcundeafen(interaction: discord.Interaction, user: discord.Member):
    """Voice channel undeafen"""
    if not user.voice:
        await interaction.response.send_message("❌ User is not in a voice channel!", ephemeral=True)
        return
    
    await user.edit(deafen=False)
    log_action(interaction.guild.id, user.id, interaction.user.id, 
               "Voice Undeafen", "Undeafened in voice channel")
    
    await interaction.response.send_message(
        embed=discord.Embed(
            description=f"✅ Undeafened {user.mention} in voice channel",
            color=discord.Color.green()
        )
    )

# ==================== MOVE MESSAGES COMMAND ====================
@bot.tree.command(name="movemsg", description="Move recent messages to another channel")
@app_commands.describe(
    amount="Number of messages to move (1-50)",
    destination="Channel to move messages to"
)
@is_mod_or_admin()
async def movemsg(interaction: discord.Interaction, amount: int, 
                  destination: discord.TextChannel):
    """Move messages to another channel"""
    if amount < 1 or amount > 50:
        await interaction.response.send_message("❌ Amount must be between 1 and 50!", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    messages = []
    async for message in interaction.channel.history(limit=amount):
        messages.append(message)
    
    messages.reverse()  # Chronological order
    
    for msg in messages:
        embed = discord.Embed(
            description=msg.content or "*[No text content]*",
            color=discord.Color.blue(),
            timestamp=msg.created_at
        )
        embed.set_author(name=msg.author.name, icon_url=msg.author.display_avatar.url)
        
        if msg.attachments:
            embed.add_field(name="Attachments", value="\n".join([a.url for a in msg.attachments]))
        
        await destination.send(embed=embed)
    
    await interaction.followup.send(
        f"✅ Moved {len(messages)} message(s) to {destination.mention}",
        ephemeral=True
    )

# ==================== WHOIS COMMAND ====================
@bot.tree.command(name="whois", description="Detailed information about a user")
@app_commands.describe(user="User to lookup")
@is_mod_or_admin()
async def whois(interaction: discord.Interaction, user: discord.Member):
    """Detailed user lookup"""
    embed = discord.Embed(
        title=f"📋 Detailed Info - {user.name}",
        color=user.color,
        timestamp=discord.utils.utcnow()
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    
    # Basic info
    embed.add_field(name="User ID", value=user.id, inline=True)
    embed.add_field(name="Nickname", value=user.display_name, inline=True)
    embed.add_field(name="Bot", value="Yes" if user.bot else "No", inline=True)
    
    # Dates
    embed.add_field(name="Account Created", 
                   value=f"<t:{int(user.created_at.timestamp())}:F>", inline=False)
    if user.joined_at:
        embed.add_field(name="Joined Server", 
                       value=f"<t:{int(user.joined_at.timestamp())}:F>", inline=False)
    
    # Roles
    roles = [role.mention for role in user.roles if role.name != "@everyone"]
    embed.add_field(name=f"Roles ({len(roles)})", 
                   value=" ".join(roles) if roles else "No roles", inline=False)
    
    # Permissions
    key_perms = []
    if user.guild_permissions.administrator:
        key_perms.append("Administrator")
    if user.guild_permissions.manage_guild:
        key_perms.append("Manage Server")
    if user.guild_permissions.manage_channels:
        key_perms.append("Manage Channels")
    if user.guild_permissions.kick_members:
        key_perms.append("Kick Members")
    if user.guild_permissions.ban_members:
        key_perms.append("Ban Members")
    
    if key_perms:
        embed.add_field(name="Key Permissions", value=", ".join(key_perms), inline=False)
    
    # Moderation stats
    warnings = get_warnings(interaction.guild.id, user.id)
    history = get_mod_history(interaction.guild.id, user.id, 1)
    embed.add_field(name="Total Warnings", value=str(len(warnings)), inline=True)
    embed.add_field(name="Mod Actions", value=str(len(history)), inline=True)
    
    # Status
    if user.voice:
        embed.add_field(name="Voice Channel", value=user.voice.channel.name, inline=False)
    
    await interaction.response.send_message(embed=embed)


# ==================== RUN BOT ====================
if __name__ == "__main__":
    bot.run(BOT_TOKEN)